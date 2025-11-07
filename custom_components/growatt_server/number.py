"""Number platform for Growatt."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from growattServer import DeviceType, GrowattV1ApiError, OpenApiV1

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrowattConfigEntry, GrowattCoordinator
from .sensor.sensor_entity_description import GrowattRequiredKeysMixin

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = (
    1  # Serialize updates as inverter does not handle concurrent requests
)


@dataclass(frozen=True, kw_only=True)
class GrowattNumberEntityDescription(NumberEntityDescription, GrowattRequiredKeysMixin):
    """Describes Growatt number entity."""

    write_key: str | None = None  # Parameter ID for writing (if different from api_key)


# Note that the Growatt V1 API uses different keys for reading and writing parameters.
# Reading values returns camelCase keys, while writing requires snake_case keys.

MIN_NUMBER_TYPES: tuple[GrowattNumberEntityDescription, ...] = (
    GrowattNumberEntityDescription(
        key="charge_power",
        translation_key="charge_power",
        api_key="chargePowerCommand",  # Key returned by V1 API
        write_key="charge_power",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="charge_stop_soc",
        translation_key="charge_stop_soc",
        api_key="wchargeSOCLowLimit",  # Key returned by V1 API
        write_key="charge_stop_soc",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="discharge_power",
        translation_key="discharge_power",
        api_key="disChargePowerCommand",  # Key returned by V1 API
        write_key="discharge_power",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="discharge_stop_soc",
        translation_key="discharge_stop_soc",
        api_key="wdisChargeSOCLowLimit",  # Key returned by V1 API
        write_key="discharge_stop_soc",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
)

MIX_NUMBER_TYPES: tuple[GrowattNumberEntityDescription, ...] = (
    GrowattNumberEntityDescription(
        key="charge_power",
        translation_key="charge_power",
        api_key="chargePowerCommand",  # Key returned by V1 API
        write_key="charge_power",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="charge_stop_soc",
        translation_key="charge_stop_soc",
        api_key="wchargeSOCLowLimit1",  # Key for MIX devices (time period 1)
        write_key="charge_stop_soc",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="discharge_power",
        translation_key="discharge_power",
        api_key="disChargePowerCommand",  # Key returned by V1 API
        write_key="discharge_power",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
    GrowattNumberEntityDescription(
        key="discharge_stop_soc",
        translation_key="discharge_stop_soc",
        api_key="loadFirstStopSocSet",  # Key returned by V1 API for MIX devices
        write_key="discharge_stop_soc",  # Key used to write parameter
        native_step=1,
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
    ),
)


class GrowattNumber(CoordinatorEntity[GrowattCoordinator], NumberEntity):
    """Representation of a Growatt number."""

    _attr_has_entity_name = True
    entity_description: GrowattNumberEntityDescription

    def __init__(
        self,
        coordinator: GrowattCoordinator,
        description: GrowattNumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )

    @property
    def native_value(self) -> int | None:
        """Return the current value of the number."""
        value = self.coordinator.get_value(self.entity_description)
        if value is None:
            return None
        return int(value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value of the number."""
        try:
            # Convert float to int for API
            int_value = int(value)

            # Determine device type based on coordinator device type
            if self.coordinator.device_type == "tlx":
                device_type = DeviceType.MIN_TLX
            else:  # mix
                device_type = DeviceType.SPH_MIX

            # Get the command name from write_key
            key = self.entity_description.key

            if self.coordinator.device_type == "mix":
                # MIX devices require full parameter sets for charge/discharge time periods
                if key in ("charge_power", "charge_stop_soc"):
                    # Updating charge parameters - need all charge time period params
                    command = "mix_ac_charge_time_period"

                    # Get current values from coordinator data
                    current_charge_power = self.coordinator.data.get(
                        "chargePowerCommand", 80
                    )
                    current_charge_soc = self.coordinator.data.get(
                        "wchargeSOCLowLimit1", 100
                    )
                    current_ac_charge = self.coordinator.data.get("acChargeEnable", 1)
                    # Get the time period enable switch (separate from AC charge enable)
                    period_enabled = self.coordinator.data.get(
                        "forcedChargeStopSwitch1", 1
                    )

                    # Parse time from "HH:MM" format, default to 14:00-16:00
                    charge_start_str = self.coordinator.data.get(
                        "forcedChargeTimeStart1", "14:0"
                    )
                    charge_stop_str = self.coordinator.data.get(
                        "forcedChargeTimeStop1", "16:0"
                    )

                    try:
                        start_parts = charge_start_str.split(":")
                        start_hour = int(start_parts[0])
                        start_minute = int(start_parts[1])
                    except (ValueError, IndexError, AttributeError):
                        start_hour, start_minute = 14, 0

                    try:
                        stop_parts = charge_stop_str.split(":")
                        end_hour = int(stop_parts[0])
                        end_minute = int(stop_parts[1])
                    except (ValueError, IndexError, AttributeError):
                        end_hour, end_minute = 16, 0

                    # Update the value being changed
                    if key == "charge_power":
                        current_charge_power = int_value
                    else:  # charge_stop_soc
                        current_charge_soc = int_value

                    params = OpenApiV1.MixAcChargeTimeParams(
                        charge_power=int(current_charge_power),
                        charge_stop_soc=int(current_charge_soc),
                        mains_enabled=bool(current_ac_charge),
                        start_hour=start_hour,
                        start_minute=start_minute,
                        end_hour=end_hour,
                        end_minute=end_minute,
                        enabled=bool(period_enabled),
                        segment_id=1,
                    )

                else:  # discharge_power or discharge_stop_soc
                    # Updating discharge parameters - need all discharge time period params
                    command = "mix_ac_discharge_time_period"

                    # Get current values from coordinator data
                    current_discharge_power = self.coordinator.data.get(
                        "disChargePowerCommand", 100
                    )
                    current_discharge_soc = self.coordinator.data.get(
                        "loadFirstStopSocSet", 10
                    )
                    # Get the time period enable switch
                    period_enabled = self.coordinator.data.get(
                        "forcedDischargeStopSwitch1", 0
                    )

                    # Parse time from "HH:MM" format, default to 00:00-00:00 (disabled)
                    discharge_start_str = self.coordinator.data.get(
                        "forcedDischargeTimeStart1", "0:0"
                    )
                    discharge_stop_str = self.coordinator.data.get(
                        "forcedDischargeTimeStop1", "0:0"
                    )

                    try:
                        start_parts = discharge_start_str.split(":")
                        start_hour = int(start_parts[0])
                        start_minute = int(start_parts[1])
                    except (ValueError, IndexError, AttributeError):
                        start_hour, start_minute = 0, 0

                    try:
                        stop_parts = discharge_stop_str.split(":")
                        end_hour = int(stop_parts[0])
                        end_minute = int(stop_parts[1])
                    except (ValueError, IndexError, AttributeError):
                        end_hour, end_minute = 0, 0

                    # Update the value being changed
                    if key == "discharge_power":
                        current_discharge_power = int_value
                    else:  # discharge_stop_soc
                        current_discharge_soc = int_value

                    params = OpenApiV1.MixAcDischargeTimeParams(
                        discharge_power=int(current_discharge_power),
                        discharge_stop_soc=int(current_discharge_soc),
                        start_hour=start_hour,
                        start_minute=start_minute,
                        end_hour=end_hour,
                        end_minute=end_minute,
                        enabled=bool(period_enabled),
                        segment_id=1,
                    )

            else:
                # MIN/TLX devices use individual ChargeDischargeParams commands
                command = (
                    self.entity_description.write_key or self.entity_description.api_key
                )
                params = OpenApiV1.ChargeDischargeParams(
                    charge_power=int_value if key == "charge_power" else 0,
                    charge_stop_soc=int_value if key == "charge_stop_soc" else 0,
                    discharge_power=int_value if key == "discharge_power" else 0,
                    discharge_stop_soc=int_value if key == "discharge_stop_soc" else 0,
                    ac_charge_enabled=False,
                )

            _LOGGER.debug(
                "Setting %s to %s for device type %s (command: %s)",
                key,
                int_value,
                device_type,
                command,
            )

            # Use V1 API to write parameter
            await self.hass.async_add_executor_job(
                self.coordinator.api.write_parameter,
                self.coordinator.device_id,
                device_type,
                command,
                params,
            )

            _LOGGER.debug(
                "Successfully set %s to %s",
                key,
                int_value,
            )

            # If no exception was raised, the write was successful
            # Update the value in coordinator
            self.coordinator.set_value(self.entity_description, int_value)
            self.async_write_ha_state()

        except GrowattV1ApiError as e:
            msg = f"Error while setting parameter: {e}"
            _LOGGER.exception(msg)
            raise HomeAssistantError(msg) from e


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Growatt number entities."""
    runtime_data = entry.runtime_data

    entities: list[GrowattNumber] = []

    # Add number entities for each device (only supported with V1 API)
    for device_coordinator in runtime_data.devices.values():
        if device_coordinator.api_version == "v1":
            # Use appropriate number types based on device type
            if device_coordinator.device_type == "tlx":
                number_types = MIN_NUMBER_TYPES
            else:  # mix
                number_types = MIX_NUMBER_TYPES

            entities.extend(
                GrowattNumber(
                    coordinator=device_coordinator,
                    description=description,
                )
                for description in number_types
            )

    async_add_entities(entities)
