"""The Growatt server PV inverter sensor integration."""

import asyncio
import logging
from collections.abc import Mapping

import requests
import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, HomeAssistantError
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.util import dt as dt_util

from . import growattServer
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
        if device_type == growattServer.DeviceType.MIX_SPH:
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
            growattServer.DeviceType.MIX_SPH,
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
    """Register services for MIN/TLX devices."""
    from datetime import datetime

    # Get all MIN coordinators with V1 API - single source of truth
    min_coordinators = {
        coord.device_id: coord
        for coord in device_coordinators.values()
        if coord.device_type == "min" and coord.api_version == "v1"
    }

    if not min_coordinators:
        _LOGGER.debug(
            "No MIN devices with V1 API found, skipping TOU service registration. "
            "Services require MIN devices with token authentication"
        )
        return

    _LOGGER.info(
        "Found %d MIN device(s) with V1 API, registering TOU services",
        len(min_coordinators),
    )

    def get_coordinator(device_id: str | None = None) -> GrowattCoordinator:
        """Get coordinator by device_id with consistent behavior."""
        if device_id is None:
            if len(min_coordinators) == 1:
                # Only one device - return it
                return next(iter(min_coordinators.values()))
            # Multiple devices - require explicit selection
            device_list = ", ".join(min_coordinators.keys())
            raise HomeAssistantError(
                f"Multiple MIN devices available ({device_list}). "
                "Please specify device_id parameter."
            )

        # Explicit device_id provided
        if device_id not in min_coordinators:
            raise HomeAssistantError(f"MIN device '{device_id}' not found")

        return min_coordinators[device_id]

    async def handle_update_time_segment(call: ServiceCall) -> None:
        """Handle update_time_segment service call."""
        segment_id = int(call.data["segment_id"])
        batt_mode_str = str(call.data["batt_mode"])
        start_time_str = call.data["start_time"]
        end_time_str = call.data["end_time"]
        enabled = call.data["enabled"]
        device_id = call.data.get("device_id")

        _LOGGER.debug(
            "handle_update_time_segment: segment_id=%d, batt_mode=%s, start=%s, end=%s, enabled=%s, device_id=%s",
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
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
        except ValueError as err:
            _LOGGER.error("Start_time and end_time must be in HH:MM format")
            raise HomeAssistantError(
                "start_time and end_time must be in HH:MM format"
            ) from err

        # Get the appropriate MIN coordinator
        coordinator = get_coordinator(device_id)

        try:
            await coordinator.update_time_segment(
                segment_id,
                batt_mode,
                start_time,
                end_time,
                enabled,
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
        """Handle read_time_segments service call."""
        # Get the appropriate MIN coordinator
        coordinator = get_coordinator(call.data.get("device_id"))

        try:
            time_segments = await coordinator.read_time_segments()
        except Exception as err:
            _LOGGER.error("Error reading time segments: %s", err)
            raise HomeAssistantError(f"Error reading time segments: {err}") from err
        else:
            return {"time_segments": time_segments}

    # Create device selector schema helper
    device_selector_fields = {}
    if len(min_coordinators) > 1:
        device_options = [
            selector.SelectOptionDict(value=device_id, label=f"MIN Device {device_id}")
            for device_id in min_coordinators
        ]
        device_selector_fields[vol.Required("device_id")] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=device_options)
        )

    # Define service schemas
    update_schema_fields = {
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
        vol.Required("start_time"): selector.TimeSelector(),
        vol.Required("end_time"): selector.TimeSelector(),
        vol.Required("enabled"): selector.BooleanSelector(),
        **device_selector_fields,
    }

    read_schema_fields = {**device_selector_fields}

    # Register services
    services_to_register = [
        (
            "update_time_segment",
            handle_update_time_segment,
            update_schema_fields,
        ),
        ("read_time_segments", handle_read_time_segments, read_schema_fields),
    ]

    for service_name, handler, schema_fields in services_to_register:
        if not hass.services.has_service(DOMAIN, service_name):
            schema = vol.Schema(schema_fields) if schema_fields else None
            supports_response = (
                SupportsResponse.ONLY
                if service_name == "read_time_segments"
                else SupportsResponse.NONE
            )

            hass.services.async_register(
                DOMAIN,
                service_name,
                handler,
                schema=schema,
                supports_response=supports_response,
            )
            _LOGGER.info("Registered service: %s", service_name)


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
