"""API throttling utilities for Growatt server integration."""

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Throttling configuration
API_THROTTLE_MINUTES = 5

# Storage versioning for data migration - increment when changing data format
# Version 1: Initial implementation with ISO datetime strings
# If we later change the data structure, increment to version 2 and add migration logic
STORAGE_VERSION = 1

# Storage key for persistent throttle data (saved to disk)
# This stores the actual throttle timestamps that persist across HA restarts
_STORAGE_KEY = "growatt_server.api_throttle"

# Memory key for storing the throttle manager instance in hass.data
# This stores the manager object itself in memory during HA runtime
_THROTTLE_MANAGER_KEY = "growatt_server.api_throttle_manager"


class ApiThrottleManager:
    """Manage API throttling data using Home Assistant storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the throttle manager."""
        self.hass = hass
        self._store: Store[dict[str, str]] = Store(hass, STORAGE_VERSION, _STORAGE_KEY)
        self._data: dict[str, str] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load the throttle data from storage."""
        if not self._loaded:
            data = await self._store.async_load()
            self._data = data or {}
            self._loaded = True

    async def should_throttle(self, func_name: str) -> bool:
        """Check if an API call should be throttled."""
        await self.async_load()

        # Fast path: if no previous call recorded, allow immediately
        if func_name not in self._data:
            _LOGGER.debug(
                "No previous call recorded for %s, allowing immediately", func_name
            )
            return False

        last_call_str = self._data[func_name]
        try:
            last_call = dt_util.parse_datetime(last_call_str)
            if last_call is None:
                _LOGGER.debug(
                    "Could not parse last call time for %s, allowing call", func_name
                )
                return False

            # Old format: ISO string without explicit timezone info  
            # New format: ISO string with explicit UTC timezone info
            if last_call.tzinfo is None:
                # This is likely a legacy timestamp from old torage
                # We stored UTC times but without timezone markers, so assume UTC
                _LOGGER.debug(
                    "Found legacy timestamp without timezone for %s, assuming UTC: %s", 
                    func_name, last_call_str
                )
                last_call = last_call.replace(tzinfo=dt_util.UTC)
            elif last_call.tzinfo != dt_util.UTC:
                # This shouldn't happen with either old or new format, but handle edge cases
                # where dt_util.parse_datetime() returns a non-UTC timezone
                _LOGGER.warning(
                    "Unexpected timezone %s for %s, converting to UTC", 
                    last_call.tzinfo, func_name
                )
                last_call = last_call.astimezone(dt_util.UTC)

            # Optimization: use total_seconds() to avoid object creation
            time_since_last_call = dt_util.utcnow() - last_call
            time_since_seconds = time_since_last_call.total_seconds()
            throttle_window_seconds = API_THROTTLE_MINUTES * 60

            if time_since_seconds < throttle_window_seconds:
                remaining_seconds = throttle_window_seconds - time_since_seconds
                remaining_minutes = remaining_seconds / 60
                _LOGGER.warning(
                    "THROTTLING ACTIVE for %s - last call was %.1f minutes ago, need to wait %.1f more minutes",
                    func_name,
                    time_since_seconds / 60,
                    remaining_minutes,
                )
                return True
            _LOGGER.debug(
                "Allowing %s - last call was %.1f minutes ago (> %d minute threshold)",
                func_name,
                time_since_seconds / 60,
                API_THROTTLE_MINUTES,
            )
        except (ValueError, TypeError) as e:
            # If we can't parse the timestamp, allow the call (fail-safe)
            _LOGGER.warning(
                "Could not parse timestamp for %s (%s), allowing call (fail-safe)",
                func_name,
                e,
            )

        return False

    async def get_throttle_data(self) -> dict[str, str]:
        """Get the current throttle data."""
        await self.async_load()
        return self._data.copy()

    async def record_api_call(self, func_name: str) -> None:
        """Record that an API call was made."""
        await self.async_load()

        # Ensure we store UTC timestamp with explicit timezone info
        current_time = dt_util.utcnow().replace(tzinfo=dt_util.UTC).isoformat()
        self._data[func_name] = current_time
        _LOGGER.debug("Recording API call for %s at %s", func_name, current_time)
        self._store.async_delay_save(self._data.copy, delay=1)

    async def throttled_call(self, func, *args, **kwargs) -> Any:
        """Execute a function call with throttling protection.

        Args:
            func: The function to call
            *args: Positional arguments to pass to func
            **kwargs: Keyword arguments to pass to func

        Returns:
            The result of the function call
        """
        func_name = func.__name__
        _LOGGER.debug("Attempting throttled call to %s", func_name)

        # Check if we should throttle based on function name
        if await self.should_throttle(func_name):
            _LOGGER.warning(
                "Throttling %s - Home Assistant will automatically retry in a few minutes",
                func_name,
            )
            raise ConfigEntryNotReady(
                f"API calls to {func_name} rate-limited to prevent account lock-out. Home Assistant will automatically retry when the cooldown period expires. Just hold on"
            )

        # Record this API call attempt
        await self.record_api_call(func_name)
        _LOGGER.debug("Executing %s (not throttled)", func_name)

        # Execute the function - use executor for sync functions
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await self.hass.async_add_executor_job(func, *args, **kwargs)
        except Exception as e:
            _LOGGER.error("Error executing %s: %s", func_name, e)
            raise

        _LOGGER.debug("Successfully completed %s", func_name)
        return result


def init_throttle_manager(hass: HomeAssistant) -> ApiThrottleManager:
    """Initialize the throttle manager and store it in hass.data."""
    if _THROTTLE_MANAGER_KEY not in hass.data:
        hass.data[_THROTTLE_MANAGER_KEY] = ApiThrottleManager(hass)
    return hass.data[_THROTTLE_MANAGER_KEY]
