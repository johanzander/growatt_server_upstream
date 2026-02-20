"""The Growatt server PV inverter sensor integration."""

import asyncio
from collections.abc import Mapping
from json import JSONDecodeError
import logging

import growattServer
from requests import RequestException

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    AUTH_API_TOKEN,
    AUTH_PASSWORD,
    CACHED_API_KEY,
    CONF_AUTH_TYPE,
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
from .services import async_register_services
from .throttle import API_THROTTLE_MINUTES, init_throttle_manager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Device types supported by the Open API V1 (type id → deviceType string)
V1_DEVICE_TYPES: dict[int, str] = {5: "sph", 7: "min"}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Growatt Server component."""
    # Register services
    await async_register_services(hass)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version > 1:
        # User has downgraded from a future version
        return False

    # Migrate from version 1.0 to 1.1
    if config_entry.version == 1 and config_entry.minor_version < 1:
        config = config_entry.data

        # First, ensure auth_type field exists (legacy config entry migration)
        # This handles config entries created before auth_type was introduced
        if CONF_AUTH_TYPE not in config:
            new_data = dict(config_entry.data)
            # Detect auth type based on which fields are present
            if CONF_TOKEN in config:
                new_data[CONF_AUTH_TYPE] = AUTH_API_TOKEN
                hass.config_entries.async_update_entry(config_entry, data=new_data)
                config = config_entry.data
                _LOGGER.debug("Added auth_type field to V1 API config entry")
            elif CONF_USERNAME in config:
                new_data[CONF_AUTH_TYPE] = AUTH_PASSWORD
                hass.config_entries.async_update_entry(config_entry, data=new_data)
                config = config_entry.data
                _LOGGER.debug("Added auth_type field to Classic API config entry")
            else:
                # Config entry has no auth fields - this is invalid but migration
                # should still succeed. Setup will fail later with a clearer error.
                _LOGGER.warning(
                    "Config entry has no authentication fields. "
                    "Setup will fail until the integration is reconfigured"
                )

        # Handle DEFAULT_PLANT_ID resolution
        if config.get(CONF_PLANT_ID) == DEFAULT_PLANT_ID:
            # V1 API should never have DEFAULT_PLANT_ID (plant selection happens in config flow)
            # If it does, this indicates a corrupted config entry
            if config.get(CONF_AUTH_TYPE) == AUTH_API_TOKEN:
                _LOGGER.error(
                    "V1 API config entry has DEFAULT_PLANT_ID, which indicates a "
                    "corrupted configuration. Please reconfigure the integration"
                )
                return False

            # Classic API with DEFAULT_PLANT_ID - resolve to actual plant_id
            if config.get(CONF_AUTH_TYPE) == AUTH_PASSWORD:
                username = config.get(CONF_USERNAME)
                password = config.get(CONF_PASSWORD)
                url = config.get(CONF_URL, DEFAULT_URL)

                if not username or not password:
                    # Credentials missing - cannot migrate
                    _LOGGER.error(
                        "Cannot migrate DEFAULT_PLANT_ID due to missing credentials"
                    )
                    return False

                try:
                    # Create API instance and login
                    api = growattServer.GrowattApi(
                        add_random_user_id=True, agent_identifier=username
                    )
                    api.server_url = url

                    login_response = await hass.async_add_executor_job(
                        api.login, username, password
                    )
                    if not login_response.get("success"):
                        _LOGGER.error(
                            "Migration failed: Unable to login to fetch plant_id"
                        )
                        return False

                    user_id = login_response["user"]["id"]

                    # Resolve DEFAULT_PLANT_ID to actual plant_id
                    plant_info = await hass.async_add_executor_job(
                        api.plant_list, user_id
                    )
                except (RequestException, JSONDecodeError) as ex:
                    # API failure during migration - return False to retry later
                    _LOGGER.error(
                        "Failed to resolve plant_id during migration: %s. "
                        "Migration will retry on next restart",
                        ex,
                    )
                    return False

                if not plant_info or "data" not in plant_info or not plant_info["data"]:
                    _LOGGER.error(
                        "No plants found for this account. "
                        "Migration will retry on next restart"
                    )
                    return False

                first_plant_id = plant_info["data"][0]["plantId"]

                # Update config entry with resolved plant_id
                new_data = dict(config_entry.data)
                new_data[CONF_PLANT_ID] = first_plant_id
                hass.config_entries.async_update_entry(
                    config_entry, data=new_data, minor_version=1
                )

                # Cache the logged-in API instance for reuse in async_setup_entry()
                hass.data.setdefault(DOMAIN, {})
                cache_key = f"{CACHED_API_KEY}{config_entry.entry_id}"
                hass.data[DOMAIN][cache_key] = api
                _LOGGER.debug("Cached authenticated API with key %s", cache_key)

                _LOGGER.info(
                    "Migrated config entry to use specific plant_id '%s'",
                    first_plant_id,
                )
        else:
            # No DEFAULT_PLANT_ID to resolve, just bump version
            hass.config_entries.async_update_entry(config_entry, minor_version=1)

        _LOGGER.debug("Migration completed to version %s.%s", config_entry.version, 1)

    return True


def get_device_list_classic(
    api: growattServer.GrowattApi, config: Mapping[str, str]
) -> tuple[list[dict[str, str]], str]:
    """Retrieve the device list for the selected plant."""
    plant_id = config[CONF_PLANT_ID]

    # Log in to api and fetch first plant if no plant id is defined.
    try:
        login_response = api.login(config[CONF_USERNAME], config[CONF_PASSWORD])
    except (RequestException, JSONDecodeError) as ex:
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

    # Legacy support: DEFAULT_PLANT_ID ("0") triggers auto-selection of first plant.
    # Modern config flow always sets a specific plant_id, but old config entries
    # from earlier versions may still have plant_id="0".
    if plant_id == DEFAULT_PLANT_ID:
        try:
            plant_info = api.plant_list(user_id)
        except (RequestException, JSONDecodeError) as ex:
            raise ConfigEntryError(
                f"Error communicating with Growatt API during plant list: {ex}"
            ) from ex
        if not plant_info or "data" not in plant_info or not plant_info["data"]:
            raise ConfigEntryError("No plants found for this account.")
        plant_id = plant_info["data"][0]["plantId"]

    # Get a list of devices for specified plant to add sensors for.
    try:
        devices = api.device_list(plant_id)
    except (RequestException, JSONDecodeError) as ex:
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
    supported_devices = [
        {
            "deviceSn": device.get("device_sn", ""),
            "deviceType": V1_DEVICE_TYPES[device.get("type")],
        }
        for device in devices
        if device.get("type") in V1_DEVICE_TYPES
    ]

    for device in devices:
        if device.get("type") not in V1_DEVICE_TYPES:
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
    # Defensive: api_version is hardcoded in async_setup_entry as "v1" or "classic"
    # This line is unreachable through normal execution but kept as a safeguard
    raise ConfigEntryError(f"Unknown API version: {api_version}")  # pragma: no cover


async def _setup_coordinators_and_platforms(
    hass: HomeAssistant,
    config_entry: GrowattConfigEntry,
    api,
    api_version: str,
    throttle_manager,
) -> None:
    """Set up coordinators and platforms (common logic for immediate and delayed setup)."""
    config = config_entry.data
    
    # Get device list (with throttling for Classic API)
    if api_version == "classic":
        devices, plant_id = await throttle_manager.throttled_call(
            get_device_list_classic, api, config
        )
    else:
        devices, plant_id = await hass.async_add_executor_job(
            get_device_list, api, config, api_version
        )

    # Store API in runtime_data early so coordinators can access it
    config_entry.runtime_data = GrowattRuntimeData(
        api=api,
        total_coordinator=None,  # type: ignore[arg-type]
        devices={},
    )

    # Create coordinators
    total_coordinator = GrowattCoordinator(
        hass, config_entry, plant_id, "total", plant_id
    )

    device_coordinators = {
        device["deviceSn"]: GrowattCoordinator(
            hass,
            config_entry,
            device["deviceSn"],
            device["deviceType"],
            plant_id,
        )
        for device in devices
        if device["deviceType"] in ["inverter", "tlx", "storage", "mix", "min", "sph"]
    }

    # Perform first refresh
    await total_coordinator.async_config_entry_first_refresh()
    for device_coordinator in device_coordinators.values():
        await device_coordinator.async_config_entry_first_refresh()

    # Update runtime data with coordinators
    config_entry.runtime_data = GrowattRuntimeData(
        api=api,
        total_coordinator=total_coordinator,
        devices=device_coordinators,
    )

    # Set up all the entities
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)


def _format_time(minutes: float) -> str:
    """Format minutes as human-readable time string."""
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


async def _handle_throttled_setup(
    hass: HomeAssistant,
    config_entry: GrowattConfigEntry,
    api,
    api_version: str,
    throttle_manager,
    minutes_remaining: float,
) -> None:
    """Handle setup when throttled - wait and then complete setup."""
    _LOGGER.warning(
        "Setup throttled - need to wait %.1f more minutes (entry_id: %s)",
        minutes_remaining,
        config_entry.entry_id,
    )

    time_str = _format_time(minutes_remaining)
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
    config_entry.runtime_data = GrowattRuntimeData(
        api=api,
        total_coordinator=None,  # type: ignore[arg-type]
        devices={},
    )

    async def delayed_setup():
        """Wait for throttle period and complete setup."""
        remaining_seconds = minutes_remaining * 60
        
        # Wait with live countdown updates
        while remaining_seconds > 0:
            wait_chunk = min(30, remaining_seconds)
            await asyncio.sleep(wait_chunk)
            remaining_seconds -= wait_chunk

            if remaining_seconds > 0:
                remaining_minutes = remaining_seconds / 60
                time_str = _format_time(remaining_minutes)
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

        _LOGGER.info(
            "Throttle period expired, completing setup (entry_id: %s)",
            config_entry.entry_id,
        )

        try:
            await _setup_coordinators_and_platforms(
                hass, config_entry, api, api_version, throttle_manager
            )
            _LOGGER.info(
                "Successfully completed delayed setup for Growatt integration (entry_id: %s)",
                config_entry.entry_id,
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


async def async_setup_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Set up Growatt from a config entry."""
    _LOGGER.debug("async_setup_entry called for entry_id=%s", config_entry.entry_id)

    config = config_entry.data
    url = config.get(CONF_URL, DEFAULT_URL)

    # If the URL has been deprecated then change to the default instead
    if url in DEPRECATED_URLS:
        url = DEFAULT_URL
        new_data = dict(config_entry.data)
        new_data[CONF_URL] = url
        hass.config_entries.async_update_entry(config_entry, data=new_data)

    # Migrate legacy config entries without auth_type field
    if CONF_AUTH_TYPE not in config:
        new_data = dict(config_entry.data)
        # Detect auth type based on which fields are present
        if CONF_TOKEN in config:
            new_data[CONF_AUTH_TYPE] = AUTH_API_TOKEN
        elif CONF_USERNAME in config:
            new_data[CONF_AUTH_TYPE] = AUTH_PASSWORD
        else:
            raise ConfigEntryError(
                "Unable to determine authentication type from config entry."
            )
        hass.config_entries.async_update_entry(config_entry, data=new_data)
        config = config_entry.data

    # Determine API version and get API instance
    # Note: auth_type field is guaranteed to exist after migration
    if config.get(CONF_AUTH_TYPE) == AUTH_API_TOKEN:
        # V1 API (token-based, no login needed)
        token = config[CONF_TOKEN]
        api = growattServer.OpenApiV1(token=token)
        plant_id = config[CONF_PLANT_ID]
    elif config.get(CONF_AUTH_TYPE) == AUTH_PASSWORD:
        # Classic API (username/password with login)
        username = config[CONF_USERNAME]
        password = config[CONF_PASSWORD]
        plant_id = config[CONF_PLANT_ID]

        # Check if migration cached an authenticated API instance for us to reuse.
        # This avoids calling login() twice (once in migration, once here) which
        # would trigger rate limiting.
        cache_key = f"{CACHED_API_KEY}{config_entry.entry_id}"
        cached_api = hass.data.get(DOMAIN, {}).pop(cache_key, None)
        
        _LOGGER.debug(
            "Checking for cached API with key %s: %s",
            cache_key,
            "found" if cached_api else "not found",
        )

        if cached_api:
            # Reuse the logged-in API instance from migration (rate limit optimization)
            api = cached_api
            _LOGGER.debug("Reusing logged-in session from migration")
        else:
            # No cached API (normal setup or migration didn't run)
            # Create and login to API
            api = growattServer.GrowattApi(
                add_random_user_id=True, agent_identifier=username
            )
            api.server_url = url
            login_response = await hass.async_add_executor_job(
                api.login, username, password
            )
            if not login_response.get("success"):
                raise ConfigEntryAuthFailed("Login failed")
    else:
        raise ConfigEntryError("Unknown authentication type in config entry.")

    # Store API in runtime_data IMMEDIATELY so coordinators can access it
    # This ensures all coordinators share the same logged-in API instance
    config_entry.runtime_data = GrowattRuntimeData(
        api=api,
        total_coordinator=None,  # Will be set below
        devices={},  # Will be populated below
    )

    # Get device list using the authenticated API (via throttle if Classic API)
    if config.get(CONF_AUTH_TYPE) == AUTH_API_TOKEN:
        devices, plant_id = await hass.async_add_executor_job(
            get_device_list_v1, api, config
        )
    else:
        # Classic API: Use throttle manager to prevent rate limiting
        devices = await hass.async_add_executor_job(api.device_list, plant_id)

    # Create a coordinator for the total sensors
    total_coordinator = GrowattCoordinator(
        hass, config_entry, plant_id, "total", plant_id
    )

    # Create coordinators for individual devices
    device_coordinators = {
        device["deviceSn"]: GrowattCoordinator(
            hass,
            config_entry,
            device["deviceSn"],
            device["deviceType"],
            plant_id,
        )
        for device in devices
        if device["deviceType"] in ["inverter", "tlx", "storage", "mix", "min", "sph"]
    }

    # Update runtime_data with coordinators
    config_entry.runtime_data = GrowattRuntimeData(
        api=api,
        total_coordinator=total_coordinator,
        devices=device_coordinators,
    )

    # Perform initial refresh for all coordinators
    await total_coordinator.async_config_entry_first_refresh()

    for coordinator in device_coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: GrowattConfigEntry
) -> bool:
    """Unload a config entry."""
    # Only try to unload platforms if they were actually loaded
    # This prevents errors when setup failed or was delayed due to throttling
    if (
        hasattr(config_entry, "runtime_data")
        and config_entry.runtime_data is not None
        and config_entry.runtime_data.total_coordinator is not None
    ):
        return await hass.config_entries.async_unload_platforms(
            config_entry, PLATFORMS
        )

    # No platforms were loaded, so unload is automatically successful
    _LOGGER.debug(
        "No platforms to unload for entry %s (setup never completed or was throttled)",
        config_entry.entry_id,
    )
    return True
