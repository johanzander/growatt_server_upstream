"""Tests for the Growatt Server throttle functionality."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util

from custom_components.growatt_server.throttle import (
    API_THROTTLE_MINUTES,
    ApiThrottleManager,
    init_throttle_manager,
)

# Mark all tests in this file to disable throttle mocking
pytestmark = pytest.mark.no_throttle_mock


@pytest.fixture
async def throttle_manager(hass: HomeAssistant) -> ApiThrottleManager:
    """Create a throttle manager for testing."""
    manager = ApiThrottleManager(hass)
    await manager.async_load()
    return manager


async def test_init_throttle_manager(hass: HomeAssistant) -> None:
    """Test initializing the throttle manager."""
    manager1 = init_throttle_manager(hass)
    assert isinstance(manager1, ApiThrottleManager)

    # Should return the same instance on second call
    manager2 = init_throttle_manager(hass)
    assert manager1 is manager2


async def test_no_throttle_on_first_call(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test that the first API call is not throttled."""
    should_throttle = await throttle_manager.should_throttle("test_function")
    assert should_throttle is False


async def test_throttle_after_recent_call(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
) -> None:
    """Test that API calls are throttled within the throttle window."""
    # Record an API call with a timestamp 2 minutes ago
    past_time = dt_util.utcnow() - timedelta(minutes=2)
    past_timestamp = past_time.replace(tzinfo=dt_util.UTC).isoformat()
    throttle_manager._data["test_function"] = past_timestamp
    throttle_manager._loaded = True

    # Should be throttled (2 minutes < 5 minute window)
    should_throttle = await throttle_manager.should_throttle("test_function")
    assert should_throttle is True


async def test_no_throttle_after_window_expires(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
) -> None:
    """Test that throttling expires after the throttle window."""
    # Record an API call with a timestamp 6 minutes ago
    past_time = dt_util.utcnow() - timedelta(minutes=API_THROTTLE_MINUTES + 1)
    past_timestamp = past_time.replace(tzinfo=dt_util.UTC).isoformat()
    throttle_manager._data["test_function"] = past_timestamp
    throttle_manager._loaded = True

    # Should not be throttled (6 minutes > 5 minute window)
    should_throttle = await throttle_manager.should_throttle("test_function")
    assert should_throttle is False


async def test_throttle_different_functions_independently(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
) -> None:
    """Test that different functions are throttled independently."""
    # Record calls with timestamps at different times
    time_now = dt_util.utcnow()

    # function_a was called 4 minutes ago
    function_a_time = time_now - timedelta(minutes=4)
    throttle_manager._data["function_a"] = function_a_time.replace(
        tzinfo=dt_util.UTC
    ).isoformat()

    # function_b was called 2 minutes ago
    function_b_time = time_now - timedelta(minutes=2)
    throttle_manager._data["function_b"] = function_b_time.replace(
        tzinfo=dt_util.UTC
    ).isoformat()

    throttle_manager._loaded = True

    # function_a should still be throttled (4 minutes < 5)
    assert await throttle_manager.should_throttle("function_a") is True

    # function_b should still be throttled (2 minutes < 5)
    assert await throttle_manager.should_throttle("function_b") is True

    # Now set function_a to 6 minutes ago (past threshold)
    function_a_time = time_now - timedelta(minutes=6)
    throttle_manager._data["function_a"] = function_a_time.replace(
        tzinfo=dt_util.UTC
    ).isoformat()

    # function_a should not be throttled (6 minutes > 5)
    assert await throttle_manager.should_throttle("function_a") is False

    # function_b should still be throttled (2 minutes < 5)
    assert await throttle_manager.should_throttle("function_b") is True


async def test_get_throttle_data(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
) -> None:
    """Test retrieving throttle data."""
    # Record some API calls
    await throttle_manager.record_api_call("function_a")
    await throttle_manager.record_api_call("function_b")

    # Get the throttle data
    data = await throttle_manager.get_throttle_data()

    # Should have entries for both functions
    assert "function_a" in data
    assert "function_b" in data

    # Should be ISO format timestamps
    assert isinstance(data["function_a"], str)
    assert isinstance(data["function_b"], str)

    # Should be able to parse the timestamps
    dt_util.parse_datetime(data["function_a"])
    dt_util.parse_datetime(data["function_b"])


async def test_throttled_call_success(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test successful execution of a throttled call."""
    mock_func = Mock(return_value="test_result")
    mock_func.__name__ = "test_function"

    result = await throttle_manager.throttled_call(mock_func)

    assert result == "test_result"
    mock_func.assert_called_once()


async def test_throttled_call_async_function(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test throttled call with an async function."""
    mock_async_func = AsyncMock(return_value="async_result")
    mock_async_func.__name__ = "async_function"

    result = await throttle_manager.throttled_call(mock_async_func, "arg1")

    assert result == "async_result"
    mock_async_func.assert_called_once_with("arg1")


async def test_throttled_call_raises_config_entry_not_ready(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
) -> None:
    """Test that throttled call raises ConfigEntryNotReady when throttled."""
    mock_func = Mock(return_value="test_result")
    mock_func.__name__ = "test_function"

    # Simulate a recent call by inserting a timestamp 2 minutes ago
    past_time = dt_util.utcnow() - timedelta(minutes=2)
    past_timestamp = past_time.replace(tzinfo=dt_util.UTC).isoformat()
    throttle_manager._data["test_function"] = past_timestamp
    throttle_manager._loaded = True

    # Call should raise ConfigEntryNotReady because it's within throttle window
    with pytest.raises(ConfigEntryNotReady, match="rate-limited"):
        await throttle_manager.throttled_call(mock_func)


async def test_throttled_call_propagates_exceptions(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test that throttled call propagates exceptions from the function."""
    mock_func = Mock(side_effect=ValueError("test error"))
    mock_func.__name__ = "failing_function"

    with pytest.raises(ValueError, match="test error"):
        await throttle_manager.throttled_call(mock_func)


async def test_record_api_call_stores_utc_timestamp(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test that API call records store UTC timestamps."""
    await throttle_manager.record_api_call("test_function")

    data = await throttle_manager.get_throttle_data()
    timestamp_str = data["test_function"]

    # Parse the timestamp
    timestamp = dt_util.parse_datetime(timestamp_str)
    assert timestamp is not None

    # Should have explicit timezone info
    assert timestamp.tzinfo is not None
    # Should be UTC
    assert timestamp.tzinfo == dt_util.UTC


async def test_legacy_timestamp_handling(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test handling of legacy timestamps without timezone info."""
    # Simulate a legacy timestamp (ISO format without timezone) from 2 minutes ago
    past_time = dt_util.utcnow() - timedelta(minutes=2)
    legacy_time = past_time.replace(tzinfo=None)
    legacy_timestamp = legacy_time.isoformat()

    # Manually insert legacy timestamp
    throttle_manager._data["legacy_function"] = legacy_timestamp
    throttle_manager._loaded = True

    # Should handle legacy timestamp without crashing and should be throttled
    should_throttle = await throttle_manager.should_throttle("legacy_function")

    # Should be throttled (within 5 minute window)
    assert should_throttle is True


async def test_invalid_timestamp_allows_call(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test that invalid timestamps allow the call (fail-safe)."""
    # Insert an invalid timestamp
    throttle_manager._data["broken_function"] = "not-a-valid-timestamp"
    throttle_manager._loaded = True

    # Should allow the call (fail-safe behavior)
    should_throttle = await throttle_manager.should_throttle("broken_function")
    assert should_throttle is False


async def test_persistence_across_loads(
    hass: HomeAssistant, throttle_manager: ApiThrottleManager
) -> None:
    """Test that throttle data persists across loads."""
    import asyncio

    # Record an API call
    await throttle_manager.record_api_call("persistent_function")

    # Get the initial data
    initial_data = await throttle_manager.get_throttle_data()
    assert "persistent_function" in initial_data

    # Wait for the delayed save to complete (delay=1 second in record_api_call)
    await asyncio.sleep(1.5)
    await hass.async_block_till_done()

    # Create a new manager instance (simulating HA restart)
    new_manager = ApiThrottleManager(hass)
    await new_manager.async_load()

    # Data should still be there
    new_data = await new_manager.get_throttle_data()
    assert "persistent_function" in new_data
    assert new_data["persistent_function"] == initial_data["persistent_function"]


async def test_throttle_exact_boundary(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test throttling behavior at the exact boundary."""
    # Record an API call
    await throttle_manager.record_api_call("boundary_function")

    # Advance time to exactly 5 minutes
    freezer.tick(timedelta(minutes=API_THROTTLE_MINUTES))

    # Should not be throttled (>= threshold)
    should_throttle = await throttle_manager.should_throttle("boundary_function")
    assert should_throttle is False


async def test_multiple_calls_update_timestamp(
    hass: HomeAssistant,
    throttle_manager: ApiThrottleManager,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that multiple successful calls update the timestamp."""
    # First call
    await throttle_manager.record_api_call("updating_function")
    first_data = await throttle_manager.get_throttle_data()
    first_timestamp = first_data["updating_function"]

    # Wait 6 minutes (past throttle window)
    freezer.tick(timedelta(minutes=6))

    # Second call
    await throttle_manager.record_api_call("updating_function")
    second_data = await throttle_manager.get_throttle_data()
    second_timestamp = second_data["updating_function"]

    # Timestamps should be different
    assert first_timestamp != second_timestamp
