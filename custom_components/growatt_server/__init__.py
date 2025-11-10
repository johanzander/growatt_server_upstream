"""The Growatt server PV inverter sensor integration."""

import asyncio
from datetime import datetime, time
import logging
from collections.abc import Mapping

import requests
import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

import growattServer

from .const import (
    BATT_MODE_MAP,
    CONF_PLANT_ID,
    DEFAULT_PLANT_ID,
    DEFAULT_URL,
    DEPRECATED_URLS,
    DOMAIN,
    LOGIN_INVALID_AUTH_CODE,
    PLATFORMS,
)
from .coordinator import GrowattConfigEntry, GrowattCoordinator
from .models import GrowattRuntimeData
from .throttle import API_THROTTLE_MINUTES, init_throttle_manager

_LOGGER = logging.getLogger(__name__)


def get_device_list_classic(
    api: growattServer.GrowattApi, config: Mapping[str, str]
) -> tuple[list[dict[str, str]], str]:
    """Retrieve the device list for the selected plant."""
    plant_id = config[CONF_PLANT_ID]

    # Log in to api and fetch first plant if no plant id is defined.
    try:
        login_response = api.login(config[CONF_USERNAME], config[CONF_PASSWORD])
    except requests.exceptions.RequestException as ex:
        raise ConfigEntryError(f"Network error during Growatt API login: {ex}") from ex
    except ValueError as ex:
        raise ConfigEntryError(f"Invalid response format during login: {ex}") from ex
    except KeyError as ex:
        raise ConfigEntryError(f"Missing expected key in login response: {ex}") from ex

    if not login_response.get("success"):
        msg = login_response.get("msg", "Unknown error")
        _LOGGER.debug("Growatt login failed: %s", msg)
        if msg == LOGIN_INVALID_AUTH_CODE:
            raise ConfigEntryAuthFailed("Username, Password or URL may be incorrect!")
        raise ConfigEntryError(f"Growatt login failed: {msg}")

    try:
        user_id = login_response["user"]["id"]
    except KeyError as ex:
        raise ConfigEntryError(f"Missing user ID in login response: {ex}") from ex

    if plant_id == DEFAULT_PLANT_ID:
        try:
            plant_info = api.plant_list(user_id)
        except requests.exceptions.RequestException as ex:
            raise ConfigEntryError(f"Network error during plant list: {ex}") from ex
        except ValueError as ex:
            raise ConfigEntryError(
                f"Invalid response format during plant list: {ex}"
            ) from ex
        except KeyError as ex:
            raise ConfigEntryError(
                f"Missing expected key in plant list response: {ex}"
            ) from ex

        if not plant_info or "data" not in plant_info or not plant_info["data"]:
            raise ConfigEntryError("No plants found for this account.")
        plant_id = plant_info["data"][0].get("plantId")
        if not plant_id:
            raise ConfigEntryError("Plant ID missing in plant info.")

    try:
        devices = api.device_list(plant_id)
    except requests.exceptions.RequestException as ex:
        raise ConfigEntryError(f"Network error during device list: {ex}") from ex
    except ValueError as ex:
        raise ConfigEntryError(
            f"Invalid response format during device list: {ex}"
        ) from ex
    except KeyError as ex:
        raise ConfigEntryError(
            f"Missing expected key in device list response: {ex}"
        ) from ex

    return devices, plant_id


def get_device_list_v1(
    api, config: Mapping[str, str]
) -> tuple[list[dict[str, str]], str]:
    """
    Device list logic for Open API V1.

    Note: Plant selection (including auto-selection if only one plant exists)
    is handled in the config flow before this function is called. This function
    only fetches devices for the already-selected plant_id.
    """
    plant_id = config[CONF_PLANT_ID]
    try:
        devices = api.get_devices(plant_id)
    except growattServer.GrowattV1ApiError as e:
        error_code = getattr(e, "error_code", None)
        error_msg = getattr(e, "error_msg", None)
        msg = (
            f"API error during device list: {e} "
            f"(Code: {error_code}, "
            f"Message: {error_msg})"
        )
        raise ConfigEntryError(msg) from e

    # Only MIX (type =5 ) MIN (type = 7)  device support implemented in current V1 API
    # Only include supported device types: MIX (type=5) and MIN (type=7)
    supported_devices = []
    for device in devices:
        device_type = device.device_type
        device_sn = device.device_sn
        # Use integer values directly if MIX and MIN are not defined in DeviceType
        if device_type == growattServer.DeviceType.SPH_MIX:
            supported_devices.append(
                {
                    "deviceSn": device_sn,
                    "deviceType": "mix",
                }
            )
        elif device_type == growattServer.DeviceType.MIN_TLX:
            supported_devices.append(
                {
                    "deviceSn": device_sn,
                    "deviceType": "min",
                }
            )

    for device in devices:
        if device.device_type not in (
            growattServer.DeviceType.SPH_MIX,
            growattServer.DeviceType.MIN_TLX,
        ):
            _LOGGER.warning(
                "Device %s with type %s not supported in Open API V1, skipping",
                device.device_sn,
                device.device_type,
            )
    return supported_devices, plant_id


def get_device_list(
    api: "growattServer.GrowattApi",
    config: Mapping[str, str],
    api_version: str,
) -> tuple[list[dict[str, str]], str]:
    """Dispatch to correct device list logic based on API version."""
    if api_version == "v1":
        return get_device_list_v1(api, config)
    if api_version == "classic":
        return get_device_list_classic(api, config)
    msg = f"Unknown API version: {api_version}"
    raise ConfigEntryError(msg)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Set up Growatt from a config entry."""
    _LOGGER.debug(
        "Setting up Growatt integration (entry_id: %s, title: %s)",
        config_entry.entry_id,
        config_entry.title,
    )

    config = config_entry.data
    url = config.get(CONF_URL, DEFAULT_URL)

    # If the URL has been deprecated then change to the default instead
    if url in DEPRECATED_URLS:
        url = DEFAULT_URL
        new_data = dict(config_entry.data)
        new_data[CONF_URL] = url
        hass.config_entries.async_update_entry(config_entry, data=new_data)

    # Migration: Add auth_type for older config entries
    if "auth_type" not in config:
        _LOGGER.info("Migrating config entry to add auth_type field")
        migration_data = dict(config_entry.data)
        if "token" in config:
            # Has token field, so it's V1 API
            migration_data["auth_type"] = "api_token"
        elif CONF_USERNAME in config and CONF_PASSWORD in config:
            # Has username/password, so it's Classic API
            migration_data["auth_type"] = "password"
        else:
            # Unable to determine - default to password auth
            migration_data["auth_type"] = "password"

        hass.config_entries.async_update_entry(config_entry, data=migration_data)
        config = config_entry.data

    # Determine API version
    if config.get("auth_type") == "api_token":
        api_version = "v1"
        token = config["token"]
        api = growattServer.OpenApiV1(token=token)
        _LOGGER.debug("Using Open API V1 with token authentication")
    elif config.get("auth_type") == "password":
        api_version = "classic"
        username = config[CONF_USERNAME]
        api = growattServer.GrowattApi(
            add_random_user_id=True, agent_identifier=username
        )
        api.server_url = url
        _LOGGER.debug(
            "Using Classic API with password authentication for user: %s", username
        )
    else:
        raise ConfigEntryError("Unknown authentication type in config entry.")

    # Initialize throttle manager early and store in hass.data
    throttle_manager = init_throttle_manager(hass)

    # Check if we should be throttled BEFORE attempting any API call
    if api_version == "classic":
        _LOGGER.debug(
            "Checking throttle status for setup (entry_id: %s)", config_entry.entry_id
        )
        # Check throttle status without making the API call
        await throttle_manager.async_load()
        func_name = get_device_list_classic.__name__
        should_throttle = await throttle_manager.should_throttle(func_name)

        # Calculate remaining minutes if throttled
        minutes_remaining = 0.0
        throttle_data = await throttle_manager.get_throttle_data()
        if should_throttle and func_name in throttle_data:
            last_call_str = throttle_data[func_name]
            last_call = dt_util.parse_datetime(last_call_str)
            if last_call:
                # Ensure timezone-aware UTC for comparison
                if last_call.tzinfo is None:
                    last_call = last_call.replace(tzinfo=dt_util.UTC)
                elif last_call.tzinfo != dt_util.UTC:
                    last_call = last_call.astimezone(dt_util.UTC)
                elapsed_seconds = (dt_util.utcnow() - last_call).total_seconds()
                remaining_seconds = (API_THROTTLE_MINUTES * 60) - elapsed_seconds
                minutes_remaining = max(0, remaining_seconds / 60)

        _LOGGER.debug(
            "Throttle check result: should_throttle=%s, minutes_remaining=%.1f",
            should_throttle,
            minutes_remaining,
        )

        if should_throttle:
            _LOGGER.warning(
                "Setup throttled - need to wait %.1f more minutes (entry_id: %s)",
                minutes_remaining,
                config_entry.entry_id,
            )

            # Format time
            def format_time(minutes: float) -> str:
                if minutes < 1:
                    seconds = int(minutes * 60)
                    return f"{seconds} seconds"
                mins = int(minutes)
                secs = int((minutes - mins) * 60)
                if mins > 0 and secs > 0:
                    return f"{mins}:{secs:02d}"
                if mins > 0:
                    return f"{mins} minute{'s' if mins != 1 else ''}"
                return f"{secs} seconds"

            # Create a persistent notification with countdown
            time_str = format_time(minutes_remaining)
            persistent_notification.async_create(
                hass,
                f"🛡️ **Growatt API Rate Limited - Auto-retry in {time_str}**\n\n"
                f"This protects your account from being locked out. "
                f"Setup will continue automatically - no restart needed.\n\n"
                f"⏰ **Wait Time:** {time_str} remaining\n"
                f"🔄 **Status:** Waiting for rate limit cooldown\n"
                f"✅ **Action:** Nothing required - automatic retry",
                title="Growatt Server - Rate Limited",
                notification_id=f"growatt_throttle_{config_entry.entry_id}",
            )

            # Create placeholder runtime data to avoid errors during throttling
            # We'll replace this with real coordinators after throttle period
            # Using type: ignore since this is temporary placeholder state
            config_entry.runtime_data = GrowattRuntimeData(
                total_coordinator=None,  # type: ignore[arg-type]
                devices={},
            )

            # Schedule delayed setup
            async def delayed_setup():
                # Wait for throttle period with live updates
                remaining_seconds = minutes_remaining * 60
                while remaining_seconds > 0:
                    wait_chunk = min(30, remaining_seconds)  # Update every 30 seconds
                    await asyncio.sleep(wait_chunk)
                    remaining_seconds -= wait_chunk

                    # Update notification with countdown
                    if remaining_seconds > 0:
                        remaining_minutes = remaining_seconds / 60
                        time_str = format_time(remaining_minutes)
                        persistent_notification.async_create(
                            hass,
                            f"🛡️ **Growatt API Rate Limited - Auto-retry in {time_str}**\n\n"
                            f"Setup will continue automatically - no restart needed.\n\n"
                            f"⏰ **Wait Time:** {time_str} remaining\n"
                            f"🔄 **Status:** Waiting for rate limit cooldown",
                            title="Growatt Server - Rate Limited",
                            notification_id=f"growatt_throttle_{config_entry.entry_id}",
                        )

                # Dismiss notification
                persistent_notification.async_dismiss(
                    hass, f"growatt_throttle_{config_entry.entry_id}"
                )

                # Complete the real setup now
                _LOGGER.info(
                    "Throttle period expired, completing setup (entry_id: %s)",
                    config_entry.entry_id,
                )

                try:
                    # Get device list with proper async/sync pattern
                    if api_version == "v1":
                        devices, plant_id = await hass.async_add_executor_job(
                            get_device_list, api, config, api_version
                        )
                    elif api_version == "classic":
                        # Use throttled version - call directly on the manager!
                        devices, plant_id = await throttle_manager.throttled_call(
                            get_device_list_classic, api, config
                        )
                    else:
                        _LOGGER.error(
                            "Unknown API version during delayed setup: %s", api_version
                        )
                        return

                    _LOGGER.info(
                        "Retrieved %d devices for plant %s", len(devices), plant_id
                    )

                    # Create a coordinator for the total sensors
                    total_coordinator = GrowattCoordinator(
                        hass, config_entry, plant_id, "total", plant_id
                    )

                    # Create coordinators for each device
                    device_coordinators = {
                        device["deviceSn"]: GrowattCoordinator(
                            hass,
                            config_entry,
                            device["deviceSn"],
                            device["deviceType"],
                            plant_id,
                        )
                        for device in devices
                        if device["deviceType"]
                        in ["inverter", "tlx", "storage", "mix", "min"]
                    }

                    # Perform the first refresh for the total coordinator
                    await total_coordinator.async_refresh()

                    # Perform the first refresh for each device coordinator
                    for device_coordinator in device_coordinators.values():
                        await device_coordinator.async_refresh()

                    # Update runtime data with real coordinators
                    config_entry.runtime_data = GrowattRuntimeData(
                        total_coordinator=total_coordinator,
                        devices=device_coordinators,
                    )

                    # Set up all the entities
                    await hass.config_entries.async_forward_entry_setups(
                        config_entry, PLATFORMS
                    )

                    _LOGGER.info(
                        "Successfully completed delayed setup for Growatt integration (entry_id: %s) with %d devices",
                        config_entry.entry_id,
                        len(device_coordinators),
                    )

                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("Failed to complete delayed setup: %s", err)
                    persistent_notification.async_create(
                        hass,
                        f"⚠️ **Growatt Setup Failed**\n\nError: {err}\n\nPlease disable and re-enable the integration.",
                        title="Growatt Server - Setup Error",
                        notification_id=f"growatt_error_{config_entry.entry_id}",
                    )

            # Start the delayed setup task
            hass.async_create_task(delayed_setup())

            # Return True - setup "succeeded" but in throttled state
            return True

    # Get device list with proper async/sync pattern
    if api_version == "v1":
        devices, plant_id = await hass.async_add_executor_job(
            get_device_list, api, config, api_version
        )
    elif api_version == "classic":
        # Use throttled version - call directly on the manager!
        devices, plant_id = await throttle_manager.throttled_call(
            get_device_list_classic, api, config
        )
    else:
        raise ConfigEntryError(f"Unknown API version: {api_version}")

    _LOGGER.info("Retrieved %d devices for plant %s", len(devices), plant_id)

    # Create a coordinator for the total sensors
    total_coordinator = GrowattCoordinator(
        hass, config_entry, plant_id, "total", plant_id
    )

    # Create coordinators for each device
    device_coordinators = {
        device["deviceSn"]: GrowattCoordinator(
            hass, config_entry, device["deviceSn"], device["deviceType"], plant_id
        )
        for device in devices
        if device["deviceType"] in ["inverter", "tlx", "storage", "mix", "min"]
    }

    # Perform the first refresh for the total coordinator
    await total_coordinator.async_config_entry_first_refresh()

    # Perform the first refresh for each device coordinator
    for device_coordinator in device_coordinators.values():
        await device_coordinator.async_config_entry_first_refresh()

    # Store runtime data in the config entry
    config_entry.runtime_data = GrowattRuntimeData(
        total_coordinator=total_coordinator,
        devices=device_coordinators,
    )

    # Set up all the entities
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Register services for MIN/TLX devices (TOU settings)
    await _async_register_services(hass, config_entry, device_coordinators)

    _LOGGER.info(
        "Successfully set up Growatt integration (entry_id: %s) with %d devices",
        config_entry.entry_id,
        len(device_coordinators),
    )
    return True


async def _async_register_services(
    hass: HomeAssistant,
    config_entry: GrowattConfigEntry,
    device_coordinators: dict,
) -> None:
    """Register time-of-use (TOU) services for inverters with V1 API."""
    # Only register services if we have V1 API devices that support TOU
    _LOGGER.debug(
        "Checking for V1 API devices to register TOU services. Devices: %s",
        [
            (coord.device_id, coord.device_type, coord.api_version)
            for coord in device_coordinators.values()
        ],
    )

    v1_devices = {
        device_id: coord
        for device_id, coord in device_coordinators.items()
        if coord.device_type in ("tlx", "mix") and coord.api_version == "v1"
    }

    if not v1_devices:
        _LOGGER.warning(
            "No V1 API devices found, skipping TOU service registration. "
            "Services require TLX/MIX devices with token authentication"
        )
        return

    _LOGGER.info("Found V1 API device(s), registering TOU services")

    def get_coordinator(device_id: str | None = None) -> GrowattCoordinator:
        """Get coordinator by device_id with consistent behavior."""
        if device_id is None:
            if len(v1_devices) == 1:
                # Only one device - return it
                return next(iter(v1_devices.values()))
            # Multiple devices - require explicit selection
            device_list = ", ".join(v1_devices.keys())
            raise HomeAssistantError(
                f"Multiple V1 devices available ({device_list}). "
                "Please specify device_id parameter."
            )
        # Explicit device_id provided
        if device_id not in v1_devices:
            raise HomeAssistantError(f"V1 device '{device_id}' not found")

        _LOGGER.debug("Found V1 device: %s", device_id)
        _LOGGER.debug("V1 device details: %s", v1_devices[device_id])

        return v1_devices[device_id]

    async def handle_update_time_segment(call: ServiceCall) -> None:
        """Handle update_time_segment service call."""
        segment_id = int(call.data["segment_id"])
        batt_mode_str = str(call.data["batt_mode"])
        start_time_str = call.data["start_time"]
        end_time_str = call.data["end_time"]
        enabled = call.data["enabled"]
        device_id = call.data.get("device_id")

        # SPH_MIX specific parameters (optional) - ensure they are integers
        charge_power = int(call.data.get("charge_power", 80))
        charge_stop_soc = int(call.data.get("charge_stop_soc", 95))
        mains_enabled = call.data.get("mains_enabled", True)

        _LOGGER.debug(
            "handle_update_time_segment: segment_id=%d, batt_mode=%s, start=%s, end=%s, enabled=%s, device_id=%s, charge_power=%d, charge_stop_soc=%d, mains_enabled=%s",
            segment_id,
            batt_mode_str,
            start_time_str,
            end_time_str,
            enabled,
            device_id,
            charge_power,
            charge_stop_soc,
            mains_enabled,
        )

        # Convert batt_mode string to integer
        batt_mode = BATT_MODE_MAP.get(batt_mode_str)
        if batt_mode is None:
            _LOGGER.error("Invalid battery mode: %s", batt_mode_str)
            raise HomeAssistantError(f"Invalid battery mode: {batt_mode_str}")

        # Convert time strings to datetime.time objects
        try:
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)
        except ValueError as err:
            _LOGGER.error("Start_time and end_time must be in HH:MM format")
            raise HomeAssistantError(
                "start_time and end_time must be in HH:MM format"
            ) from err

        # Get the appropriate coordinator
        coordinator = get_coordinator(device_id)

        try:
            return await coordinator.update_time_segment(
                segment_id,
                batt_mode,
                start_time,
                end_time,
                enabled,
                charge_power=charge_power,
                charge_stop_soc=charge_stop_soc,
                mains_enabled=mains_enabled,
            )
        except Exception as err:
            _LOGGER.error(
                "Error updating time segment %d: %s",
                segment_id,
                err,
            )
            raise HomeAssistantError(
                f"Error updating time segment {segment_id}: {err}"
            ) from err

    async def handle_read_time_segments(call: ServiceCall) -> dict:
        """Handle read_min_time_segments service call."""

        _LOGGER.debug("CALL: %s", call.data)
        device_id = "EGM2H4L0G0"

        # # Handle device_id being passed as a list (extract first element)
        # if isinstance(device_id, list):
        #     device_id = device_id[0] if device_id else None

        _LOGGER.info("handle_read_time_segments() called with device_id=%s", device_id)
        coordinator = get_coordinator(device_id)

        if coordinator is None:
            raise HomeAssistantError(
                "No V1 API device found (requires TLX/MIX with token authentication)"
            )

        try:
            time_segments = await coordinator.read_time_segments()
        except Exception as err:
            _LOGGER.error("Error reading time segments: %s", err)
            raise HomeAssistantError(f"Error reading time segments: {err}") from err
        else:
            return {"time_segments": time_segments}

    async def handle_update_time_segment_tlx(call: ServiceCall) -> None:
        """Handle update_time_segment_tlx service call (TLX-specific)."""
        segment_id = int(call.data["segment_id"])
        batt_mode_str = str(call.data["batt_mode"])
        start_time_str = call.data["start_time"]
        end_time_str = call.data["end_time"]
        enabled = call.data["enabled"]
        device_id = call.data.get("device_id")

        _LOGGER.debug(
            "handle_update_time_segment_tlx: segment_id=%d, batt_mode=%s, start=%s, end=%s, enabled=%s, device_id=%s",
            segment_id,
            batt_mode_str,
            start_time_str,
            end_time_str,
            enabled,
            device_id,
        )

        # Convert batt_mode string to integer
        batt_mode = BATT_MODE_MAP.get(batt_mode_str)
        if batt_mode is None:
            _LOGGER.error("Invalid battery mode: %s", batt_mode_str)
            raise HomeAssistantError(f"Invalid battery mode: {batt_mode_str}")

        # Convert time strings to datetime.time objects
        try:
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)
        except ValueError as err:
            _LOGGER.error("Start_time and end_time must be in HH:MM format")
            raise HomeAssistantError(
                "start_time and end_time must be in HH:MM format"
            ) from err

        # Get the appropriate coordinator (TLX only)
        coordinator = get_coordinator(device_id)
        if coordinator.device_type != "tlx":
            raise HomeAssistantError(
                f"Device {device_id or 'default'} is not a TLX device. Use update_time_segment_mix for MIX devices."
            )

        try:
            # TLX devices use basic parameters without charge_power/SOC
            return await coordinator.update_time_segment(
                segment_id,
                batt_mode,
                start_time,
                end_time,
                enabled,
            )
        except Exception as err:
            _LOGGER.error(
                "Error updating TLX time segment %d: %s",
                segment_id,
                err,
            )
            raise HomeAssistantError(
                f"Error updating TLX time segment {segment_id}: {err}"
            ) from err

    async def handle_update_time_segment_mix(call: ServiceCall) -> None:
        """Handle update_time_segment_mix service call (MIX-specific)."""
        segment_id = int(call.data["segment_id"])
        batt_mode_str = str(call.data["batt_mode"])
        start_time_str = call.data["start_time"]
        end_time_str = call.data["end_time"]
        enabled = call.data["enabled"]
        device_id = call.data.get("device_id")

        # MIX specific parameters - ensure they are integers
        charge_power = int(call.data.get("charge_power", 80))
        charge_stop_soc = int(call.data.get("charge_stop_soc", 95))
        mains_enabled = call.data.get("mains_enabled", True)

        _LOGGER.debug(
            "handle_update_time_segment_mix: segment_id=%d, batt_mode=%s, start=%s, end=%s, enabled=%s, device_id=%s, charge_power=%d, charge_stop_soc=%d, mains_enabled=%s",
            segment_id,
            batt_mode_str,
            start_time_str,
            end_time_str,
            enabled,
            device_id,
            charge_power,
            charge_stop_soc,
            mains_enabled,
        )

        # Convert batt_mode string to integer
        batt_mode = BATT_MODE_MAP.get(batt_mode_str)
        if batt_mode is None:
            _LOGGER.error("Invalid battery mode: %s", batt_mode_str)
            raise HomeAssistantError(f"Invalid battery mode: {batt_mode_str}")

        # Convert time strings to datetime.time objects
        try:
            start_time = time.fromisoformat(start_time_str)
            end_time = time.fromisoformat(end_time_str)
        except ValueError as err:
            _LOGGER.error("Start_time and end_time must be in HH:MM format")
            raise HomeAssistantError(
                "start_time and end_time must be in HH:MM format"
            ) from err

        # Get the appropriate coordinator (MIX only)
        coordinator = get_coordinator(device_id)
        if coordinator.device_type != "mix":
            raise HomeAssistantError(
                f"Device {device_id or 'default'} is not a MIX device. Use update_time_segment_tlx for TLX devices."
            )

        try:
            return await coordinator.update_time_segment(
                segment_id,
                batt_mode,
                start_time,
                end_time,
                enabled,
                charge_power=charge_power,
                charge_stop_soc=charge_stop_soc,
                mains_enabled=mains_enabled,
            )
        except Exception as err:
            _LOGGER.error(
                "Error updating MIX time segment %d: %s",
                segment_id,
                err,
            )
            raise HomeAssistantError(
                f"Error updating MIX time segment {segment_id}: {err}"
            ) from err

    async def handle_read_time_segments_tlx(call: ServiceCall) -> dict:
        """Handle read_time_segments_tlx service call (TLX-specific)."""
        device_id = call.data.get("device_id")

        _LOGGER.info(
            "handle_read_time_segments_tlx() called with device_id=%s", device_id
        )
        coordinator = get_coordinator(device_id)

        if coordinator.device_type != "tlx":
            raise HomeAssistantError(
                f"Device {device_id or 'default'} is not a TLX device. Use read_time_segments_mix for MIX devices."
            )

        try:
            time_segments = await coordinator.read_time_segments()
        except Exception as err:
            _LOGGER.error("Error reading TLX time segments: %s", err)
            raise HomeAssistantError(f"Error reading TLX time segments: {err}") from err
        else:
            return {"time_segments": time_segments}

    async def handle_read_time_segments_mix(call: ServiceCall) -> dict:
        """Handle read_time_segments_mix service call (MIX-specific)."""
        device_id = call.data.get("device_id")

        _LOGGER.info(
            "handle_read_time_segments_mix() called with device_id=%s", device_id
        )
        coordinator = get_coordinator(device_id)

        if coordinator.device_type != "mix":
            raise HomeAssistantError(
                f"Device {device_id or 'default'} is not a MIX device. Use read_time_segments_tlx for TLX devices."
            )

        try:
            time_segments = await coordinator.read_time_segments()
        except Exception as err:
            _LOGGER.error("Error reading MIX time segments: %s", err)
            raise HomeAssistantError(f"Error reading MIX time segments: {err}") from err
        else:
            return {"time_segments": time_segments}

    # Common fields for all device types
    common_fields = {
        vol.Optional("device_id"): vol.Any(str, None),
        vol.Required("segment_id"): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=9, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required("batt_mode"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value="load-first", label="Load First"),
                    selector.SelectOptionDict(
                        value="battery-first", label="Battery First"
                    ),
                    selector.SelectOptionDict(value="grid-first", label="Grid First"),
                ]
            )
        ),
        vol.Required(
            "start_time", description={"suggested_value": "08:00:00"}
        ): selector.TimeSelector(selector.TimeSelectorConfig()),
        vol.Required(
            "end_time", description={"suggested_value": "17:00:00"}
        ): selector.TimeSelector(selector.TimeSelectorConfig()),
        vol.Required("enabled"): selector.BooleanSelector(),
    }

    # SPH_MIX specific fields
    mix_fields = {
        vol.Optional("charge_power", default=80): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=100,
                step=1,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.SLIDER,
            )
        ),
        vol.Optional("charge_stop_soc", default=95): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=100,
                step=1,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.SLIDER,
            )
        ),
        vol.Optional("mains_enabled", default=True): selector.BooleanSelector(),
    }

    # MIN_TLX specific fields
    min_fields = {
        vol.Required("segment_id"): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=9, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Optional("mains_enabled", default=True): selector.BooleanSelector(),
    }

    # Determine which fields to include based on available devices
    device_types = {coord.device_type for coord in v1_devices.values()}

    # Build schema based on device types present
    if "mix" in device_types and "tlx" in device_types:
        # Both device types - include all fields (user will see all options)
        update_time_segment_fields = {**common_fields, **mix_fields}
        _LOGGER.info(
            "Registering update_time_segment with fields for both MIX and TLX devices"
        )
    elif "mix" in device_types:
        # Only MIX devices - include MIX-specific fields
        update_time_segment_fields = {**common_fields, **mix_fields}
        _LOGGER.info(
            "Registering update_time_segment with MIX-specific fields "
            "(charge_power, charge_stop_soc, mains_enabled)"
        )
    else:
        # Only TLX devices or no specific detection - use common fields only
        update_time_segment_fields = {**common_fields, **min_fields}
        _LOGGER.info(
            "Registering update_time_segment with TLX-only fields "
            "(no MIX-specific parameters)"
        )
    read_time_segments_fields = {
        vol.Optional("device_id", default=None): vol.Any(str, None),
    }

    # TLX-specific schema (no MIX fields)
    tlx_update_fields = {**common_fields}

    # MIX-specific schema (includes charge parameters)
    mix_update_fields = {**common_fields, **mix_fields}

    # Register the services
    if not hass.services.has_service(DOMAIN, "update_time_segment"):
        hass.services.async_register(
            DOMAIN,
            "update_time_segment",
            handle_update_time_segment,
            schema=vol.Schema(update_time_segment_fields),
        )
        _LOGGER.info("Registered service: update_time_segment")

    if not hass.services.has_service(DOMAIN, "read_time_segments"):
        hass.services.async_register(
            DOMAIN,
            "read_time_segments",
            handle_read_time_segments,
            schema=vol.Schema(read_time_segments_fields),
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.info("Registered service: read_time_segments")

    # Register device-specific services
    if "tlx" in device_types:
        if not hass.services.has_service(DOMAIN, "update_time_segment_tlx"):
            hass.services.async_register(
                DOMAIN,
                "update_time_segment_tlx",
                handle_update_time_segment_tlx,
                schema=vol.Schema(tlx_update_fields),
            )
            _LOGGER.info("Registered service: update_time_segment_tlx")

        if not hass.services.has_service(DOMAIN, "read_time_segments_tlx"):
            hass.services.async_register(
                DOMAIN,
                "read_time_segments_tlx",
                handle_read_time_segments_tlx,
                schema=vol.Schema(read_time_segments_fields),
                supports_response=SupportsResponse.ONLY,
            )
            _LOGGER.info("Registered service: read_time_segments_tlx")

    if "mix" in device_types:
        if not hass.services.has_service(DOMAIN, "update_time_segment_mix"):
            hass.services.async_register(
                DOMAIN,
                "update_time_segment_mix",
                handle_update_time_segment_mix,
                schema=vol.Schema(mix_update_fields),
            )
            _LOGGER.info("Registered service: update_time_segment_mix")

        if not hass.services.has_service(DOMAIN, "read_time_segments_mix"):
            hass.services.async_register(
                DOMAIN,
                "read_time_segments_mix",
                handle_read_time_segments_mix,
                schema=vol.Schema(read_time_segments_fields),
                supports_response=SupportsResponse.ONLY,
            )
            _LOGGER.info("Registered service: read_time_segments_mix")


async def async_unload_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        "Unloading Growatt integration (entry_id: %s, title: %s)",
        config_entry.entry_id,
        config_entry.title,
    )

    # Only try to unload platforms if they were actually loaded
    # This prevents errors when setup failed due to throttling
    if hasattr(config_entry, "runtime_data") and config_entry.runtime_data is not None:
        unload_ok = await hass.config_entries.async_unload_platforms(
            config_entry, PLATFORMS
        )
    else:
        # No platforms were loaded, so unload is automatically successful
        _LOGGER.debug(
            "No platforms to unload for entry %s (setup never completed)",
            config_entry.entry_id,
        )
        unload_ok = True

    if unload_ok:
        _LOGGER.info(
            "Successfully unloaded Growatt integration (entry_id: %s)",
            config_entry.entry_id,
        )
    else:
        _LOGGER.error(
            "Failed to unload Growatt integration (entry_id: %s)", config_entry.entry_id
        )

    return unload_ok
