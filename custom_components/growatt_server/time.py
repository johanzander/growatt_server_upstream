"""Time platform for Growatt."""

from __future__ import annotations

from datetime import time
import logging
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrowattConfigEntry, GrowattCoordinator
from .growattServer.open_api_v1 import DeviceFieldTemplates

_LOGGER = logging.getLogger(__name__)


class GrowattChargeStartTimeEntity(CoordinatorEntity[GrowattCoordinator], TimeEntity):
    """Representation of charge start time."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "charge_start_time"

    def __init__(self, coordinator: GrowattCoordinator, segment_id: int = 1) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._segment_id = segment_id
        self._attr_unique_id = f"{coordinator.device_id}_charge_start_time_{segment_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )

    def _get_field_name(self, field_type: str) -> str:
        """Get the appropriate field name based on device type."""
        if self.coordinator.device_type == "tlx":
            template = DeviceFieldTemplates.MIN_TLX_TEMPLATES[field_type]
        else:  # mix
            template = DeviceFieldTemplates.SPH_MIX_TEMPLATES_CHARGE[field_type]
        return template.format(segment_id=self._segment_id)

    @property
    def native_value(self) -> time | None:
        """Return the current time value."""
        # Get from coordinator data using correct field name
        start_field = self._get_field_name("start_time")
        start_time_str = self.coordinator.data.get(start_field, "14:00")
        try:
            parts = start_time_str.split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError):
            return time(14, 0)

    async def async_set_value(self, value: time) -> None:
        """Update the time."""
        try:
            # Get current end time and other settings using correct field names
            stop_field = self._get_field_name("stop_time")
            enabled_field = self._get_field_name("enabled")

            end_time_str = self.coordinator.data.get(stop_field, "16:00")
            end_parts = end_time_str.split(":")
            end_time = time(hour=int(end_parts[0]), minute=int(end_parts[1]))

            enabled = bool(self.coordinator.data.get(enabled_field, 0))

            # Update the time segment with new start time
            await self.coordinator.update_time_segment(
                segment_id=self._segment_id,
                batt_mode=1,  # Battery first (charge)
                start_time=value,
                end_time=end_time,
                enabled=enabled,
            )

            await self.coordinator.async_refresh()

        except Exception as err:
            _LOGGER.error("Error setting charge start time: %s", err)
            raise HomeAssistantError(f"Error setting charge start time: {err}") from err


class GrowattChargeEndTimeEntity(CoordinatorEntity[GrowattCoordinator], TimeEntity):
    """Representation of charge end time."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "charge_end_time"

    def __init__(self, coordinator: GrowattCoordinator, segment_id: int = 1) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._segment_id = segment_id
        self._attr_unique_id = f"{coordinator.device_id}_charge_end_time_{segment_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )

    def _get_field_name(self, field_type: str) -> str:
        """Get the appropriate field name based on device type."""
        if self.coordinator.device_type == "tlx":
            template = DeviceFieldTemplates.MIN_TLX_TEMPLATES[field_type]
        else:  # mix
            template = DeviceFieldTemplates.SPH_MIX_TEMPLATES_CHARGE[field_type]
        return template.format(segment_id=self._segment_id)

    @property
    def native_value(self) -> time | None:
        """Return the current time value."""
        stop_field = self._get_field_name("stop_time")
        end_time_str = self.coordinator.data.get(stop_field, "16:00")
        try:
            parts = end_time_str.split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError):
            return time(16, 0)

    async def async_set_value(self, value: time) -> None:
        """Update the time."""
        try:
            # Get current start time and other settings using correct field names
            start_field = self._get_field_name("start_time")
            enabled_field = self._get_field_name("enabled")

            start_time_str = self.coordinator.data.get(start_field, "14:00")
            start_parts = start_time_str.split(":")
            start_time = time(hour=int(start_parts[0]), minute=int(start_parts[1]))

            enabled = bool(self.coordinator.data.get(enabled_field, 0))

            # Update the time segment with new end time
            await self.coordinator.update_time_segment(
                segment_id=self._segment_id,
                batt_mode=1,  # Battery first (charge)
                start_time=start_time,
                end_time=value,
                enabled=enabled,
            )

            await self.coordinator.async_refresh()

        except Exception as err:
            _LOGGER.error("Error setting charge end time: %s", err)
            raise HomeAssistantError(f"Error setting charge end time: {err}") from err


class GrowattDischargeStartTimeEntity(
    CoordinatorEntity[GrowattCoordinator], TimeEntity
):
    """Representation of discharge start time."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "discharge_start_time"

    def __init__(self, coordinator: GrowattCoordinator, segment_id: int = 1) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._segment_id = segment_id
        self._attr_unique_id = (
            f"{coordinator.device_id}_discharge_start_time_{segment_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )

    def _get_field_name(self, field_type: str) -> str:
        """Get the appropriate field name based on device type."""
        if self.coordinator.device_type == "tlx":
            template = DeviceFieldTemplates.MIN_TLX_TEMPLATES[field_type]
        else:  # mix
            template = DeviceFieldTemplates.SPH_MIX_TEMPLATES_DIS_CHARGE[field_type]
        return template.format(segment_id=self._segment_id)

    @property
    def native_value(self) -> time | None:
        """Return the current time value."""
        start_field = self._get_field_name("start_time")
        start_time_str = self.coordinator.data.get(start_field, "00:00")
        try:
            parts = start_time_str.split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError):
            return time(0, 0)

    async def async_set_value(self, value: time) -> None:
        """Update the time."""
        try:
            # Get current end time and other settings using correct field names
            stop_field = self._get_field_name("stop_time")
            enabled_field = self._get_field_name("enabled")

            end_time_str = self.coordinator.data.get(stop_field, "00:00")
            end_parts = end_time_str.split(":")
            end_time = time(hour=int(end_parts[0]), minute=int(end_parts[1]))

            enabled = bool(self.coordinator.data.get(enabled_field, 0))

            # For MIX devices, discharge uses segments 7-12 (offset by 6)
            # For TLX devices, it's just the segment_id
            if self.coordinator.device_type == "mix":
                segment_id = self._segment_id + 6
            else:
                segment_id = self._segment_id

            # Update the time segment with new start time
            await self.coordinator.update_time_segment(
                segment_id=segment_id,
                batt_mode=2,  # Grid first (discharge)
                start_time=value,
                end_time=end_time,
                enabled=enabled,
            )

            await self.coordinator.async_refresh()

        except Exception as err:
            _LOGGER.error("Error setting discharge start time: %s", err)
            raise HomeAssistantError(
                f"Error setting discharge start time: {err}"
            ) from err


class GrowattDischargeEndTimeEntity(CoordinatorEntity[GrowattCoordinator], TimeEntity):
    """Representation of discharge end time."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "discharge_end_time"

    def __init__(self, coordinator: GrowattCoordinator, segment_id: int = 1) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._segment_id = segment_id
        self._attr_unique_id = (
            f"{coordinator.device_id}_discharge_end_time_{segment_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer="Growatt",
            name=coordinator.device_id,
        )

    def _get_field_name(self, field_type: str) -> str:
        """Get the appropriate field name based on device type."""
        if self.coordinator.device_type == "tlx":
            template = DeviceFieldTemplates.MIN_TLX_TEMPLATES[field_type]
        else:  # mix
            template = DeviceFieldTemplates.SPH_MIX_TEMPLATES_DIS_CHARGE[field_type]
        return template.format(segment_id=self._segment_id)

    @property
    def native_value(self) -> time | None:
        """Return the current time value."""
        stop_field = self._get_field_name("stop_time")
        end_time_str = self.coordinator.data.get(stop_field, "00:00")
        try:
            parts = end_time_str.split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError):
            return time(0, 0)

    async def async_set_value(self, value: time) -> None:
        """Update the time."""
        try:
            # Get current start time and other settings using correct field names
            start_field = self._get_field_name("start_time")
            enabled_field = self._get_field_name("enabled")

            start_time_str = self.coordinator.data.get(start_field, "00:00")
            start_parts = start_time_str.split(":")
            start_time = time(hour=int(start_parts[0]), minute=int(start_parts[1]))

            enabled = bool(self.coordinator.data.get(enabled_field, 0))

            # For MIX devices, discharge uses segments 7-12 (offset by 6)
            # For TLX devices, it's just the segment_id
            if self.coordinator.device_type == "mix":
                segment_id = self._segment_id + 6
            else:
                segment_id = self._segment_id

            # Update the time segment with new end time
            await self.coordinator.update_time_segment(
                segment_id=segment_id,
                batt_mode=2,  # Grid first (discharge)
                start_time=start_time,
                end_time=value,
                enabled=enabled,
            )

            await self.coordinator.async_refresh()

        except Exception as err:
            _LOGGER.error("Error setting discharge end time: %s", err)
            raise HomeAssistantError(
                f"Error setting discharge end time: {err}"
            ) from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrowattConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Growatt time entities."""
    runtime_data = entry.runtime_data
    entities: list[TimeEntity] = []

    for device_coordinator in runtime_data.devices.values():
        if device_coordinator.api_version == "v1":
            if device_coordinator.device_type == "mix":
                # Add time entities for MIX devices (first charge/discharge segment)
                # You can extend this to create entities for all 6 segments
                entities.extend(
                    [
                        GrowattChargeStartTimeEntity(device_coordinator, segment_id=1),
                        GrowattChargeEndTimeEntity(device_coordinator, segment_id=1),
                        GrowattDischargeStartTimeEntity(
                            device_coordinator, segment_id=1
                        ),
                        GrowattDischargeEndTimeEntity(device_coordinator, segment_id=1),
                    ]
                )
            elif device_coordinator.device_type == "tlx":
                # Add time entities for TLX devices (first segment)
                # TLX uses the same entities but different field names
                # You can extend this to create entities for all 9 segments
                entities.extend(
                    [
                        GrowattChargeStartTimeEntity(device_coordinator, segment_id=1),
                        GrowattChargeEndTimeEntity(device_coordinator, segment_id=1),
                        GrowattDischargeStartTimeEntity(
                            device_coordinator, segment_id=1
                        ),
                        GrowattDischargeEndTimeEntity(device_coordinator, segment_id=1),
                    ]
                )

    async_add_entities(entities)
