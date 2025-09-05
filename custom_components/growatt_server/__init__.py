"""The Growatt server PV inverter sensor integration."""

import asyncio
from collections.abc import Mapping
import logging

import growattServer

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.components import persistent_notification

from .const import (
    CONF_PLANT_ID,
    DEFAULT_PLANT_ID,
    DEFAULT_URL,
    DEPRECATED_URLS,
    LOGIN_INVALID_AUTH_CODE,
    PLATFORMS,
)
from .coordinator import GrowattConfigEntry, GrowattCoordinator
from .models import GrowattRuntimeData
from .throttle import init_throttle_manager

_LOGGER = logging.getLogger(__name__)



def get_device_list_classic(
    api: growattServer.GrowattApi, config: Mapping[str, str]
) -> tuple[list[dict[str, str]], str]:
    """Retrieve the device list for the selected plant."""
    plant_id = config[CONF_PLANT_ID]

    # Log in to api and fetch first plant if no plant id is defined.
    try:
        login_response = api.login(config[CONF_USERNAME], config[CONF_PASSWORD])
        # DEBUG: Log the actual response structure
        _LOGGER.debug("DEBUG - Login response: %s", login_response)
    except Exception as ex:
        raise ConfigEntryError(
            f"Error communicating with Growatt API during login: {ex}"
        ) from ex

    if not login_response.get("success"):
        msg = login_response.get("msg", "Unknown error")
        _LOGGER.debug("Growatt login failed: %s", msg)
        if msg == LOGIN_INVALID_AUTH_CODE:
            raise ConfigEntryAuthFailed("Username, Password or URL may be incorrect!")
        raise ConfigEntryError(f"Growatt login failed: {msg}")

    user_id = login_response["user"]["id"]

    if plant_id == DEFAULT_PLANT_ID:
        try:
            plant_info = api.plant_list(user_id)
        except Exception as ex:
            raise ConfigEntryError(
                f"Error communicating with Growatt API during plant list: {ex}"
            ) from ex
        if not plant_info or "data" not in plant_info or not plant_info["data"]:
            raise ConfigEntryError("No plants found for this account.")
        plant_id = plant_info["data"][0].get("plantId")
        if not plant_id:
            raise ConfigEntryError("Plant ID missing in plant info.")

    # Get a list of devices for specified plant to add sensors for.
    try:
        devices = api.device_list(plant_id)
    except Exception as ex:
        raise ConfigEntryError(
            f"Error communicating with Growatt API during device list: {ex}"
        ) from ex

    return devices, plant_id


def get_device_list_v1(
    api, config: Mapping[str, str]
) -> tuple[list[dict[str, str]], str]:
    """Device list logic for Open API V1.

    Note: Plant selection (including auto-selection if only one plant exists)
    is handled in the config flow before this function is called. This function
    only fetches devices for the already-selected plant_id.
    """
    plant_id = config[CONF_PLANT_ID]
    try:
        devices_dict = api.device_list(plant_id)
    except growattServer.GrowattV1ApiError as e:
        raise ConfigEntryError(
            f"API error during device list: {e} (Code: {getattr(e, 'error_code', None)}, Message: {getattr(e, 'error_msg', None)})"
        ) from e
    devices = devices_dict.get("devices", [])
    # Only MIN device (type = 7) support implemented in current V1 API
    supported_devices = [
        {
            "deviceSn": device.get("device_sn", ""),
            "deviceType": "min",
        }
        for device in devices
        if device.get("type") == 7
    ]

    for device in devices:
        if device.get("type") != 7:
            _LOGGER.warning(
                "Device %s with type %s not supported in Open API V1, skipping",
                device.get("device_sn", ""),
                device.get("type"),
            )
    return supported_devices, plant_id


def get_device_list(
    api, config: Mapping[str, str], api_version: str
) -> tuple[list[dict[str, str]], str]:
    """Dispatch to correct device list logic based on API version."""
    if api_version == "v1":
        return get_device_list_v1(api, config)
    if api_version == "classic":
        return get_device_list_classic(api, config)
    raise ConfigEntryError(f"Unknown API version: {api_version}")


async def async_setup_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Set up Growatt from a config entry."""
    _LOGGER.debug("Setting up Growatt integration (entry_id: %s, title: %s)", config_entry.entry_id, config_entry.title)

    config = config_entry.data
    url = config.get(CONF_URL, DEFAULT_URL)

    # If the URL has been deprecated then change to the default instead
    if url in DEPRECATED_URLS:
        url = DEFAULT_URL
        new_data = dict(config_entry.data)
        new_data[CONF_URL] = url
        hass.config_entries.async_update_entry(config_entry, data=new_data)

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
        _LOGGER.debug("Using Classic API with password authentication for user: %s", username)
    else:
        raise ConfigEntryError("Unknown authentication type in config entry.")

    # Initialize throttle manager early and store in hass.data
    throttle_manager = init_throttle_manager(hass)

    # Check if we should be throttled BEFORE attempting any API call
    if api_version == "classic":
        _LOGGER.debug("Checking throttle status for setup (entry_id: %s)", config_entry.entry_id)
        # Check throttle status without making the API call
        await throttle_manager._async_load()
        func_name = get_device_list_classic.__name__
        should_throttle = await throttle_manager._should_throttle(func_name)
        
        # Calculate remaining minutes if throttled
        minutes_remaining = 0.0
        if should_throttle and func_name in throttle_manager._data:
            from homeassistant.util import dt as dt_util
            from .throttle import API_THROTTLE_MINUTES
            last_call_str = throttle_manager._data[func_name]
            last_call = dt_util.parse_datetime(last_call_str)
            if last_call:
                elapsed_seconds = (dt_util.utcnow() - last_call).total_seconds()
                remaining_seconds = (API_THROTTLE_MINUTES * 60) - elapsed_seconds
                minutes_remaining = max(0, remaining_seconds / 60)
                
        _LOGGER.debug("Throttle check result: should_throttle=%s, minutes_remaining=%.1f", should_throttle, minutes_remaining)

        if should_throttle:
            _LOGGER.warning("Setup throttled - need to wait %.1f more minutes (entry_id: %s)", minutes_remaining, config_entry.entry_id)

            # Format time
            def format_time(minutes: float) -> str:
                if minutes < 1:
                    seconds = int(minutes * 60)
                    return f"{seconds} seconds"
                else:
                    mins = int(minutes)
                    secs = int((minutes - mins) * 60)
                    if mins > 0 and secs > 0:
                        return f"{mins}:{secs:02d}"
                    elif mins > 0:
                        return f"{mins} minute{'s' if mins != 1 else ''}"
                    else:
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
                notification_id=f"growatt_throttle_{config_entry.entry_id}"
            )

            # Create placeholder runtime data to avoid errors
            config_entry.runtime_data = GrowattRuntimeData(
                total_coordinator=None,
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
                            notification_id=f"growatt_throttle_{config_entry.entry_id}"
                        )

                # Dismiss notification
                persistent_notification.async_dismiss(
                    hass, f"growatt_throttle_{config_entry.entry_id}"
                )

                # Complete the real setup now
                _LOGGER.info("Throttle period expired, completing setup (entry_id: %s)", config_entry.entry_id)

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
                        _LOGGER.error("Unknown API version during delayed setup: %s", api_version)
                        return

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
                    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

                    _LOGGER.info("Successfully completed delayed setup for Growatt integration (entry_id: %s) with %d devices",
                                config_entry.entry_id, len(device_coordinators))

                except Exception as err:
                    _LOGGER.error("Failed to complete delayed setup: %s", err)
                    persistent_notification.async_create(
                        hass,
                        f"⚠️ **Growatt Setup Failed**\n\nError: {err}\n\nPlease disable and re-enable the integration.",
                        title="Growatt Server - Setup Error",
                        notification_id=f"growatt_error_{config_entry.entry_id}"
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

    _LOGGER.info("Successfully set up Growatt integration (entry_id: %s) with %d devices",
                config_entry.entry_id, len(device_coordinators))
    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Growatt integration (entry_id: %s, title: %s)", config_entry.entry_id, config_entry.title)

    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok:
        _LOGGER.info("Successfully unloaded Growatt integration (entry_id: %s)", config_entry.entry_id)
    else:
        _LOGGER.error("Failed to unload Growatt integration (entry_id: %s)", config_entry.entry_id)

    return unload_ok
