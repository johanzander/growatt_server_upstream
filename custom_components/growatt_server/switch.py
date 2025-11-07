"""Switch platform for Growatt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import logging
from re import S
from typing import Any

import voluptuous as vol
from growattServer import GrowattV1ApiError, DeviceType

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
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
class GrowattSwitchEntityDescription(SwitchEntityDescription, GrowattRequiredKeysMixin):
    """Describes Growatt switch entity."""

    write_key: str | None = None  # Parameter ID for writing (if different from api_key)
    # Default charge settings
    default_start_time: time = time(14, 0)
    default_end_time: time = time(16, 0)
    default_charge_power: int = 80
    default_charge_stop_soc: int = 95


# Note that the Growatt V1 API uses different keys for reading and writing parameters.
# Reading values returns camelCase keys, while writing requires snake_case keys.


MIN_SWITCH_TYPES: tuple[GrowattSwitchEntityDescription, ...] = (
    GrowattSwitchEntityDescription(
        key="ac_charge",
        translation_key="ac_charge",
        api_key="acChargeEnable",  # Key returned by V1 API
        write_key="ac_charge",  # Key used to write parameter
    ),
)

MIX_SWITCH_TYPES: tuple[GrowattSwitchEntityDescription, ...] = (
    GrowattSwitchEntityDescription(
        key="ac_charge",
        translation_key="ac_charge",
        api_key="acChargeEnable",  # Key returned by V1 API
        write_key="ac_charge",  # Key used to write parameter
        default_start_time=time(14, 0),
        default_end_time=time(16, 0),
        default_charge_power=80,
        default_charge_stop_soc=95,
    ),
)


class GrowattSwitch(CoordinatorEntity[GrowattCoordinator], SwitchEntity):
    """Representation of a Growatt switch."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    entity_description: GrowattSwitchEntityDescription
    _pending_state: bool | None = None
    _charge_start_time: time | None = None
    _charge_end_time: time | None = None
    _charge_power: int | None = None
    _charge_stop_soc: int | None = None

    def __init__(
        self,
        coordinator: GrowattCoordinator,
        description: GrowattSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )
        # Initialize with default times
        self._charge_start_time = description.default_start_time
        self._charge_end_time = description.default_end_time
        self._charge_power = description.default_charge_power
        self._charge_stop_soc = description.default_charge_stop_soc

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if self._pending_state is not None:
            return self._pending_state

        value = self.coordinator.get_value(self.entity_description)

        _LOGGER.debug(
            "GET switch value %s pending state %s",
            value,
            self._pending_state,
        )

        if value is None:
            return None

        # Handle both string "1" and integer 1
        if isinstance(value, str):
            return value == "1"
        return bool(int(value))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        # Extract time parameters from kwargs if provided
        start_time = kwargs.get("start_time", self._charge_start_time)
        end_time = kwargs.get("end_time", self._charge_end_time)
        charge_power = kwargs.get("charge_power", self._charge_power)
        charge_stop_soc = kwargs.get("charge_stop_soc", self._charge_stop_soc)

        await self._async_set_state(
            True,
            start_time=start_time,
            end_time=end_time,
            charge_power=charge_power,
            charge_stop_soc=charge_stop_soc,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_state(False)

    async def _async_set_state(
        self,
        state: bool,
        start_time: time | None = None,
        end_time: time | None = None,
        charge_power: int | None = None,
        charge_stop_soc: int | None = None,
    ) -> None:
        """Set the switch state."""
        try:
            # Store the pending state before making the API call
            self._pending_state = state
            self.async_write_ha_state()

            # Convert boolean to API format (1 or 0)
            enabled = 1 if state else 0

            # Use provided times or fall back to stored values
            start = (
                start_time
                or self._charge_start_time
                or self.entity_description.default_start_time
            )
            end = (
                end_time
                or self._charge_end_time
                or self.entity_description.default_end_time
            )
            power = (
                charge_power
                or self._charge_power
                or self.entity_description.default_charge_power
            )
            soc = (
                charge_stop_soc
                or self._charge_stop_soc
                or self.entity_description.default_charge_stop_soc
            )

            # Store the new values
            if start_time:
                self._charge_start_time = start_time
            if end_time:
                self._charge_end_time = end_time
            if charge_power:
                self._charge_power = charge_power
            if charge_stop_soc:
                self._charge_stop_soc = charge_stop_soc

            # Use write_key if specified, otherwise fall back to api_key
            parameter_id = (
                self.entity_description.write_key or self.entity_description.api_key
            )

            command = ("mix_ac_charge_time_period",)

            charge_params = self.coordinator.api.MixAcChargeTimeParams(
                charge_power=power,
                charge_stop_soc=soc,
                mains_enabled=True,
                start_hour=start.hour,
                start_minute=start.minute,
                end_hour=end.hour,
                end_minute=end.minute,
                enabled=enabled,
                segment_id=1,
            )

            # Use V1 API to write parameter
            await self.hass.async_add_executor_job(
                self.coordinator.api.write_parameter,
                self.coordinator.device_id,
                DeviceType.SPH_MIX,
                command,
                charge_params,
            )

            _LOGGER.debug(
                "Set switch %s to %s",
                command,
                charge_params,
            )

            # If no exception was raised, the write was successful
            # Update the value in coordinator
            self.coordinator.set_value(self.entity_description, enabled)
            self._pending_state = None
            self.async_write_ha_state()

        except GrowattV1ApiError as e:
            # Failed - revert the pending state
            self._pending_state = None
            self.async_write_ha_state()
            _LOGGER.error("Error while setting switch state: %s", e)
            raise HomeAssistantError(f"Error while setting switch state: {e}") from e


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Growatt switch entities."""
    runtime_data = entry.runtime_data

    entities: list[GrowattSwitch] = []

    # Add switch entities for each MIN device (only supported with V1 API)
    for device_coordinator in runtime_data.devices.values():
        if (
            device_coordinator.device_type in ["mix"]
            and device_coordinator.api_version == "v1"
        ):
            # Add switch entities for MIX devices
            entities.extend(
                GrowattSwitch(
                    coordinator=device_coordinator,
                    description=description,
                )
                for description in MIX_SWITCH_TYPES
            )
        if (
            device_coordinator.device_type in ["min"]
            and device_coordinator.api_version == "v1"
        ):
            # Add switch entities for MIN devices
            entities.extend(
                GrowattSwitch(
                    coordinator=device_coordinator,
                    description=description,
                )
                for description in MIN_SWITCH_TYPES
            )

    async_add_entities(entities)

    # Register service with custom fields for turn_on
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "turn_on",
        {
            vol.Optional("start_time"): cv.time,
            vol.Optional("end_time"): cv.time,
            vol.Optional("charge_power"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            ),
            vol.Optional("charge_stop_soc"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            ),
        },
        "async_turn_on",
    )
