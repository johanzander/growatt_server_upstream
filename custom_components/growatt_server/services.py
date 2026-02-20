"""Service handlers for Growatt Server integration."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import (
    BATT_MODE_BATTERY_FIRST,
    BATT_MODE_GRID_FIRST,
    BATT_MODE_LOAD_FIRST,
    DOMAIN,
)

if TYPE_CHECKING:
    from .coordinator import GrowattCoordinator


async def async_register_services(hass: HomeAssistant) -> None:
    """Register services for Growatt Server integration."""

    def get_coordinator(device_id: str, device_type: str) -> GrowattCoordinator:
        """Get a V1 API coordinator for the given device type and device registry ID."""
        coordinators: dict[str, GrowattCoordinator] = {}
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state != ConfigEntryState.LOADED:
                continue
            for coord in entry.runtime_data.devices.values():
                if coord.device_type == device_type and coord.api_version == "v1":
                    coordinators[coord.device_id] = coord

        if not coordinators:
            raise ServiceValidationError(
                f"No {device_type.upper()} devices with token authentication are configured. "
                f"Services require {device_type.upper()} devices with V1 API access."
            )

        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(device_id)

        if not device_entry:
            raise ServiceValidationError(f"Device '{device_id}' not found")

        serial_number = None
        for identifier in device_entry.identifiers:
            if identifier[0] == DOMAIN:
                serial_number = identifier[1]
                break

        if not serial_number:
            raise ServiceValidationError(
                f"Device '{device_id}' is not a Growatt device"
            )

        if serial_number not in coordinators:
            raise ServiceValidationError(
                f"Device '{serial_number}' is not configured as a {device_type.upper()} device"
            )

        return coordinators[serial_number]

    async def handle_update_time_segment(call: ServiceCall) -> None:
        """Handle update_time_segment service call."""
        segment_id: int = int(call.data["segment_id"])
        batt_mode_str: str = call.data["batt_mode"]
        start_time_str: str = call.data["start_time"]
        end_time_str: str = call.data["end_time"]
        enabled: bool = call.data["enabled"]
        device_id: str = call.data["device_id"]

        # Validate segment_id range
        if not 1 <= segment_id <= 9:
            raise ServiceValidationError(
                f"segment_id must be between 1 and 9, got {segment_id}"
            )

        # Validate and convert batt_mode string to integer
        valid_modes = {
            "load_first": BATT_MODE_LOAD_FIRST,
            "battery_first": BATT_MODE_BATTERY_FIRST,
            "grid_first": BATT_MODE_GRID_FIRST,
        }
        if batt_mode_str not in valid_modes:
            raise ServiceValidationError(
                f"batt_mode must be one of {list(valid_modes.keys())}, got '{batt_mode_str}'"
            )
        batt_mode: int = valid_modes[batt_mode_str]

        # Convert time strings to datetime.time objects
        # UI time selector sends HH:MM:SS, but we only need HH:MM (strip seconds)
        try:
            # Take only HH:MM part (ignore seconds if present)
            start_parts = start_time_str.split(":")
            start_time_hhmm = f"{start_parts[0]}:{start_parts[1]}"
            start_time = datetime.strptime(start_time_hhmm, "%H:%M").time()
        except (ValueError, IndexError) as err:
            raise ServiceValidationError(
                "start_time must be in HH:MM or HH:MM:SS format"
            ) from err

        try:
            # Take only HH:MM part (ignore seconds if present)
            end_parts = end_time_str.split(":")
            end_time_hhmm = f"{end_parts[0]}:{end_parts[1]}"
            end_time = datetime.strptime(end_time_hhmm, "%H:%M").time()
        except (ValueError, IndexError) as err:
            raise ServiceValidationError(
                "end_time must be in HH:MM or HH:MM:SS format"
            ) from err

        # Get the appropriate MIN coordinator
        coordinator: GrowattCoordinator = get_coordinator(device_id, "min")

        await coordinator.update_time_segment(
            segment_id,
            batt_mode,
            start_time,
            end_time,
            enabled,
        )

    async def handle_read_time_segments(call: ServiceCall) -> dict[str, Any]:
        """Handle read_time_segments service call."""
        device_id: str = call.data["device_id"]

        # Get the appropriate MIN coordinator
        coordinator: GrowattCoordinator = get_coordinator(device_id, "min")

        time_segments: list[dict[str, Any]] = await coordinator.read_time_segments()

        return {"time_segments": time_segments}

    def _parse_time_str(time_str: str, field_name: str) -> time:
        """Parse a time string (HH:MM or HH:MM:SS) to a datetime.time object."""
        try:
            parts = time_str.split(":")
            hhmm = f"{parts[0]}:{parts[1]}"
            return datetime.strptime(hhmm, "%H:%M").time()
        except (ValueError, IndexError) as err:
            raise ServiceValidationError(
                f"{field_name} must be in HH:MM or HH:MM:SS format"
            ) from err

    async def handle_write_ac_charge_times(call: ServiceCall) -> None:
        """Handle write_ac_charge_times service call."""
        device_id: str = call.data["device_id"]
        charge_power: int = int(call.data["charge_power"])
        charge_stop_soc: int = int(call.data["charge_stop_soc"])
        mains_enabled: bool = call.data["mains_enabled"]

        if not 0 <= charge_power <= 100:
            raise ServiceValidationError(
                f"charge_power must be between 0 and 100, got {charge_power}"
            )
        if not 0 <= charge_stop_soc <= 100:
            raise ServiceValidationError(
                f"charge_stop_soc must be between 0 and 100, got {charge_stop_soc}"
            )

        periods = []
        for i in range(1, 4):
            start = _parse_time_str(call.data[f"period_{i}_start"], f"period_{i}_start")
            end = _parse_time_str(call.data[f"period_{i}_end"], f"period_{i}_end")
            enabled: bool = call.data[f"period_{i}_enabled"]
            periods.append({"start_time": start, "end_time": end, "enabled": enabled})

        coordinator: GrowattCoordinator = get_coordinator(device_id, "sph")
        await coordinator.update_ac_charge_times(
            charge_power, charge_stop_soc, mains_enabled, periods
        )

    async def handle_write_ac_discharge_times(call: ServiceCall) -> None:
        """Handle write_ac_discharge_times service call."""
        device_id: str = call.data["device_id"]
        discharge_power: int = int(call.data["discharge_power"])
        discharge_stop_soc: int = int(call.data["discharge_stop_soc"])

        if not 0 <= discharge_power <= 100:
            raise ServiceValidationError(
                f"discharge_power must be between 0 and 100, got {discharge_power}"
            )
        if not 0 <= discharge_stop_soc <= 100:
            raise ServiceValidationError(
                f"discharge_stop_soc must be between 0 and 100, got {discharge_stop_soc}"
            )

        periods = []
        for i in range(1, 4):
            start = _parse_time_str(
                call.data[f"period_{i}_start"], f"period_{i}_start"
            )
            end = _parse_time_str(call.data[f"period_{i}_end"], f"period_{i}_end")
            enabled: bool = call.data[f"period_{i}_enabled"]
            periods.append({"start_time": start, "end_time": end, "enabled": enabled})

        coordinator: GrowattCoordinator = get_coordinator(device_id, "sph")
        await coordinator.update_ac_discharge_times(
            discharge_power, discharge_stop_soc, periods
        )

    async def handle_read_ac_charge_times(call: ServiceCall) -> dict[str, Any]:
        """Handle read_ac_charge_times service call."""
        device_id: str = call.data["device_id"]
        coordinator: GrowattCoordinator = get_coordinator(device_id, "sph")
        return await coordinator.read_ac_charge_times()

    async def handle_read_ac_discharge_times(call: ServiceCall) -> dict[str, Any]:
        """Handle read_ac_discharge_times service call."""
        device_id: str = call.data["device_id"]
        coordinator: GrowattCoordinator = get_coordinator(device_id, "sph")
        return await coordinator.read_ac_discharge_times()

    # Register services without schema - services.yaml will provide UI definition
    # Schema validation happens in the handler functions
    hass.services.async_register(
        DOMAIN,
        "update_time_segment",
        handle_update_time_segment,
        supports_response=SupportsResponse.NONE,
    )

    hass.services.async_register(
        DOMAIN,
        "read_time_segments",
        handle_read_time_segments,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "write_ac_charge_times",
        handle_write_ac_charge_times,
        supports_response=SupportsResponse.NONE,
    )

    hass.services.async_register(
        DOMAIN,
        "write_ac_discharge_times",
        handle_write_ac_discharge_times,
        supports_response=SupportsResponse.NONE,
    )

    hass.services.async_register(
        DOMAIN,
        "read_ac_charge_times",
        handle_read_ac_charge_times,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "read_ac_discharge_times",
        handle_read_ac_discharge_times,
        supports_response=SupportsResponse.ONLY,
    )
