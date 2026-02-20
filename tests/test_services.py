"""Test Growatt Server services."""

from datetime import time
from unittest.mock import patch

import growattServer
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.growatt_server.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_read_time_segments_single_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test reading time segments for single device."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test service call
    response = await hass.services.async_call(
        DOMAIN,
        "read_time_segments",
        {"device_id": device_entry.id},
        blocking=True,
        return_response=True,
    )

    assert response == snapshot


async def test_update_time_segment_charge_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test updating time segment with charge mode."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test successful update
    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 1,
            "start_time": "09:00",
            "end_time": "11:00",
            "batt_mode": "load_first",
            "enabled": True,
        },
        blocking=True,
    )

    # Verify the API was called
    mock_growatt_v1_api.min_write_time_segment.assert_called_once()


async def test_update_time_segment_discharge_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test updating time segment with discharge mode."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 2,
            "start_time": "14:00",
            "end_time": "16:00",
            "batt_mode": "battery_first",
            "enabled": True,
        },
        blocking=True,
    )

    mock_growatt_v1_api.min_write_time_segment.assert_called_once()


async def test_update_time_segment_standby_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test updating time segment with standby mode."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 3,
            "start_time": "20:00",
            "end_time": "22:00",
            "batt_mode": "grid_first",
            "enabled": True,
        },
        blocking=True,
    )

    mock_growatt_v1_api.min_write_time_segment.assert_called_once()


async def test_update_time_segment_disabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test disabling a time segment."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 1,
            "start_time": "06:00",
            "end_time": "08:00",
            "batt_mode": "load_first",
            "enabled": False,
        },
        blocking=True,
    )

    mock_growatt_v1_api.min_write_time_segment.assert_called_once()


async def test_update_time_segment_with_seconds(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test updating time segment with HH:MM:SS format from UI."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test with HH:MM:SS format (what the UI time selector sends)
    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 1,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "batt_mode": "load_first",
            "enabled": True,
        },
        blocking=True,
    )

    mock_growatt_v1_api.min_write_time_segment.assert_called_once()


async def test_update_time_segment_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test handling API error when updating time segment."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Mock API error - the library raises an exception instead of returning error dict
    mock_growatt_v1_api.min_write_time_segment.side_effect = (
        growattServer.GrowattV1ApiError(
            "Error during writing time segment 1",
            error_code=1,
            error_msg="API Error",
        )
    )

    with pytest.raises(HomeAssistantError, match="API error updating time segment"):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


async def test_no_min_devices_skips_service_registration(
    hass: HomeAssistant,
    mock_config_entry_classic: MockConfigEntry,
    mock_growatt_classic_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that services fail gracefully when no MIN devices exist."""
    # Only non-MIN devices (TLX with classic API)
    mock_growatt_classic_api.device_list.return_value = [
        {"deviceSn": "TLX123456", "deviceType": "tlx"}
    ]

    mock_config_entry_classic.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry_classic.entry_id)
    await hass.async_block_till_done()

    # Verify services are registered (they're always registered in async_setup)
    assert hass.services.has_service(DOMAIN, "update_time_segment")
    assert hass.services.has_service(DOMAIN, "read_time_segments")

    # Get the TLX device (non-MIN)
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "TLX123456")})
    assert device_entry is not None

    # But calling them with a non-MIN device should fail with appropriate error
    with pytest.raises(
        ServiceValidationError, match="No MIN devices with token authentication"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


async def test_multiple_devices_with_valid_device_id_works(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that multiple devices work when device_id is specified."""
    # Configure mock to return two MIN devices
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [
            {"device_sn": "MIN123456", "type": 7},
            {"device_sn": "MIN789012", "type": 7},
        ]
    }

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID for the first MIN device
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test update service with specific device_id (device registry ID)
    await hass.services.async_call(
        DOMAIN,
        "update_time_segment",
        {
            "device_id": device_entry.id,
            "segment_id": 1,
            "start_time": "09:00",
            "end_time": "11:00",
            "batt_mode": "load_first",
            "enabled": True,
        },
        blocking=True,
    )

    mock_growatt_v1_api.min_write_time_segment.assert_called_once()

    # Test read service with specific device_id (device registry ID)
    response = await hass.services.async_call(
        DOMAIN,
        "read_time_segments",
        {"device_id": device_entry.id},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert "time_segments" in response


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_update_time_segment_invalid_time_format(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test handling invalid time format in update_time_segment."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test with invalid time format
    with pytest.raises(
        ServiceValidationError, match="start_time must be in HH:MM or HH:MM:SS format"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "invalid",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_update_time_segment_invalid_segment_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test validation of segment_id range."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test segment_id too low
    with pytest.raises(
        ServiceValidationError, match="segment_id must be between 1 and 9"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 0,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )

    # Test segment_id too high
    with pytest.raises(
        ServiceValidationError, match="segment_id must be between 1 and 9"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 10,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_update_time_segment_invalid_batt_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test validation of batt_mode value."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test invalid batt_mode
    with pytest.raises(ServiceValidationError, match="batt_mode must be one of"):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "invalid_mode",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_read_time_segments_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test handling API error when reading time segments."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Mock API error by making coordinator.read_time_segments raise an exception
    with (
        patch(
            "homeassistant.components.growatt_server.coordinator.GrowattCoordinator.read_time_segments",
            side_effect=HomeAssistantError("API connection failed"),
        ),
        pytest.raises(HomeAssistantError, match="API connection failed"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "read_time_segments",
            {"device_id": device_entry.id},
            blocking=True,
            return_response=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_service_with_invalid_device_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test service with device ID that doesn't exist in registry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Test with invalid device_id (not in device registry)
    with pytest.raises(ServiceValidationError, match="Device '.*' not found"):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": "invalid_device_id",
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_service_with_non_growatt_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test service with device from another integration."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Create a device from a different integration
    other_device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={("other_domain", "other_device_123")},
        name="Other Device",
    )

    # Test with device from different integration
    with pytest.raises(
        ServiceValidationError, match="Device '.*' is not a Growatt device"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": other_device.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_service_with_non_min_growatt_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test service with Growatt device that is not MIN type."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Manually create a TLX device (V1 API only creates MIN devices)
    # This simulates having a non-MIN Growatt device from another source
    tlx_device = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "TLX789012")},
        name="TLX Device",
    )

    # Test with TLX device (not a MIN device)
    with pytest.raises(
        ServiceValidationError,
        match="Device 'TLX789012' is not configured as a MIN device",
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": tlx_device.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


@pytest.mark.parametrize(
    "invalid_time",
    ["25:00", "12:99", "invalid", "12"],
    ids=["invalid_hour", "invalid_minute", "non_numeric", "missing_parts"],
)
@pytest.mark.usefixtures("mock_growatt_v1_api")
async def test_update_time_segment_invalid_end_time_format(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    invalid_time: str,
) -> None:
    """Test handling invalid end_time format in update_time_segment."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Get the device registry ID
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    # Test with invalid end_time format
    with pytest.raises(
        ServiceValidationError, match="end_time must be in HH:MM or HH:MM:SS format"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": invalid_time,
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )


async def test_write_ac_charge_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test writing AC charge times for an SPH device."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    await hass.services.async_call(
        DOMAIN,
        "write_ac_charge_times",
        {
            "device_id": device_entry.id,
            "charge_power": 80,
            "charge_stop_soc": 90,
            "mains_enabled": True,
            "period_1_start": "06:00",
            "period_1_end": "08:00",
            "period_1_enabled": True,
            "period_2_start": "00:00",
            "period_2_end": "00:00",
            "period_2_enabled": False,
            "period_3_start": "00:00",
            "period_3_end": "00:00",
            "period_3_enabled": False,
        },
        blocking=True,
    )

    mock_growatt_v1_api.sph_write_ac_charge_times.assert_called_once_with(
        "SPH123456",
        80,
        90,
        True,
        [
            {"start_time": time(6, 0), "end_time": time(8, 0), "enabled": True},
            {"start_time": time(0, 0), "end_time": time(0, 0), "enabled": False},
            {"start_time": time(0, 0), "end_time": time(0, 0), "enabled": False},
        ],
    )


async def test_write_ac_discharge_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test writing AC discharge times for an SPH device."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    await hass.services.async_call(
        DOMAIN,
        "write_ac_discharge_times",
        {
            "device_id": device_entry.id,
            "discharge_power": 70,
            "discharge_stop_soc": 20,
            "period_1_start": "18:00",
            "period_1_end": "22:00",
            "period_1_enabled": True,
            "period_2_start": "00:00",
            "period_2_end": "00:00",
            "period_2_enabled": False,
            "period_3_start": "00:00",
            "period_3_end": "00:00",
            "period_3_enabled": False,
        },
        blocking=True,
    )

    mock_growatt_v1_api.sph_write_ac_discharge_times.assert_called_once_with(
        "SPH123456",
        70,
        20,
        [
            {"start_time": time(18, 0), "end_time": time(22, 0), "enabled": True},
            {"start_time": time(0, 0), "end_time": time(0, 0), "enabled": False},
            {"start_time": time(0, 0), "end_time": time(0, 0), "enabled": False},
        ],
    )


async def test_read_ac_charge_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test reading AC charge times from an SPH device."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    response = await hass.services.async_call(
        DOMAIN,
        "read_ac_charge_times",
        {"device_id": device_entry.id},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert response["charge_power"] == 60
    assert response["charge_stop_soc"] == 20
    assert response["mains_enabled"] is True
    assert len(response["periods"]) == 3
    assert response["periods"][0]["start_time"] == "06:00"
    assert response["periods"][0]["end_time"] == "08:00"
    assert response["periods"][0]["enabled"] is True


async def test_read_ac_discharge_times(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test reading AC discharge times from an SPH device."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    response = await hass.services.async_call(
        DOMAIN,
        "read_ac_discharge_times",
        {"device_id": device_entry.id},
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert response["discharge_power"] == 70
    assert response["discharge_stop_soc"] == 15
    assert len(response["periods"]) == 3
    assert response["periods"][0]["start_time"] == "18:00"
    assert response["periods"][0]["end_time"] == "22:00"
    assert response["periods"][0]["enabled"] is True


async def test_write_ac_charge_times_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test handling API error when writing AC charge times."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    mock_growatt_v1_api.sph_write_ac_charge_times.side_effect = (
        growattServer.GrowattV1ApiError(
            "Error during writing AC charge times",
            error_code=1,
            error_msg="API Error",
        )
    )

    with pytest.raises(HomeAssistantError, match="API error updating AC charge times"):
        await hass.services.async_call(
            DOMAIN,
            "write_ac_charge_times",
            {
                "device_id": device_entry.id,
                "charge_power": 80,
                "charge_stop_soc": 90,
                "mains_enabled": True,
                "period_1_start": "06:00",
                "period_1_end": "08:00",
                "period_1_enabled": True,
                "period_2_start": "00:00",
                "period_2_end": "00:00",
                "period_2_enabled": False,
                "period_3_start": "00:00",
                "period_3_end": "00:00",
                "period_3_enabled": False,
            },
            blocking=True,
        )


async def test_write_ac_discharge_times_api_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test handling API error when writing AC discharge times."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    mock_growatt_v1_api.sph_write_ac_discharge_times.side_effect = (
        growattServer.GrowattV1ApiError(
            "Error during writing AC discharge times",
            error_code=1,
            error_msg="API Error",
        )
    )

    with pytest.raises(
        HomeAssistantError, match="API error updating AC discharge times"
    ):
        await hass.services.async_call(
            DOMAIN,
            "write_ac_discharge_times",
            {
                "device_id": device_entry.id,
                "discharge_power": 70,
                "discharge_stop_soc": 20,
                "period_1_start": "18:00",
                "period_1_end": "22:00",
                "period_1_enabled": True,
                "period_2_start": "00:00",
                "period_2_end": "00:00",
                "period_2_enabled": False,
                "period_3_start": "00:00",
                "period_3_end": "00:00",
                "period_3_enabled": False,
            },
            blocking=True,
        )


async def test_no_sph_devices_fails_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that SPH services fail gracefully when no SPH devices exist."""
    # Default fixture has MIN device (type 7), not SPH
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "MIN123456")})
    assert device_entry is not None

    with pytest.raises(
        ServiceValidationError, match="No SPH devices with token authentication"
    ):
        await hass.services.async_call(
            DOMAIN,
            "write_ac_charge_times",
            {
                "device_id": device_entry.id,
                "charge_power": 80,
                "charge_stop_soc": 90,
                "mains_enabled": True,
                "period_1_start": "06:00",
                "period_1_end": "08:00",
                "period_1_enabled": True,
                "period_2_start": "00:00",
                "period_2_end": "00:00",
                "period_2_enabled": False,
                "period_3_start": "00:00",
                "period_3_end": "00:00",
                "period_3_enabled": False,
            },
            blocking=True,
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_match"),
    [
        ("charge_power", 150, "charge_power must be between 0 and 100"),
        ("charge_power", -1, "charge_power must be between 0 and 100"),
        ("charge_stop_soc", 101, "charge_stop_soc must be between 0 and 100"),
        ("charge_stop_soc", -5, "charge_stop_soc must be between 0 and 100"),
    ],
)
async def test_write_ac_charge_times_range_validation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
    field: str,
    value: int,
    expected_match: str,
) -> None:
    """Test that out-of-range charge_power and charge_stop_soc raise ServiceValidationError."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    base_data = {
        "device_id": device_entry.id,
        "charge_power": 80,
        "charge_stop_soc": 90,
        "mains_enabled": True,
        "period_1_start": "06:00",
        "period_1_end": "08:00",
        "period_1_enabled": True,
        "period_2_start": "00:00",
        "period_2_end": "00:00",
        "period_2_enabled": False,
        "period_3_start": "00:00",
        "period_3_end": "00:00",
        "period_3_enabled": False,
    }
    base_data[field] = value

    with pytest.raises(ServiceValidationError, match=expected_match):
        await hass.services.async_call(
            DOMAIN,
            "write_ac_charge_times",
            base_data,
            blocking=True,
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_match"),
    [
        ("discharge_power", 150, "discharge_power must be between 0 and 100"),
        ("discharge_power", -1, "discharge_power must be between 0 and 100"),
        ("discharge_stop_soc", 101, "discharge_stop_soc must be between 0 and 100"),
        ("discharge_stop_soc", -5, "discharge_stop_soc must be between 0 and 100"),
    ],
)
async def test_write_ac_discharge_times_range_validation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
    field: str,
    value: int,
    expected_match: str,
) -> None:
    """Test that out-of-range discharge_power and discharge_stop_soc raise ServiceValidationError."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    base_data = {
        "device_id": device_entry.id,
        "discharge_power": 70,
        "discharge_stop_soc": 20,
        "period_1_start": "18:00",
        "period_1_end": "22:00",
        "period_1_enabled": True,
        "period_2_start": "00:00",
        "period_2_end": "00:00",
        "period_2_enabled": False,
        "period_3_start": "00:00",
        "period_3_end": "00:00",
        "period_3_enabled": False,
    }
    base_data[field] = value

    with pytest.raises(ServiceValidationError, match=expected_match):
        await hass.services.async_call(
            DOMAIN,
            "write_ac_discharge_times",
            base_data,
            blocking=True,
        )


@pytest.mark.parametrize(
    ("service", "base_data"),
    [
        (
            "write_ac_charge_times",
            {
                "charge_power": 80,
                "charge_stop_soc": 90,
                "mains_enabled": True,
                "period_1_start": "INVALID",
                "period_1_end": "08:00",
                "period_1_enabled": True,
                "period_2_start": "00:00",
                "period_2_end": "00:00",
                "period_2_enabled": False,
                "period_3_start": "00:00",
                "period_3_end": "00:00",
                "period_3_enabled": False,
            },
        ),
        (
            "write_ac_discharge_times",
            {
                "discharge_power": 70,
                "discharge_stop_soc": 20,
                "period_1_start": "18:00",
                "period_1_end": "22:00",
                "period_1_enabled": True,
                "period_2_start": "00:00",
                "period_2_end": "INVALID",
                "period_2_enabled": False,
                "period_3_start": "00:00",
                "period_3_end": "00:00",
                "period_3_enabled": False,
            },
        ),
    ],
)
async def test_write_ac_times_invalid_time_format(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_growatt_v1_api,
    device_registry: dr.DeviceRegistry,
    service: str,
    base_data: dict,
) -> None:
    """Test that invalid time format raises ServiceValidationError."""
    mock_growatt_v1_api.device_list.return_value = {
        "devices": [{"device_sn": "SPH123456", "type": 5}]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "SPH123456")})
    assert device_entry is not None

    with pytest.raises(ServiceValidationError, match="must be in HH:MM"):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"device_id": device_entry.id, **base_data},
            blocking=True,
        )


async def test_service_with_unloaded_config_entry(
    hass: HomeAssistant,
    mock_config_entry_classic: MockConfigEntry,
    mock_growatt_classic_api,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test service call when config entry is not loaded."""
    # Setup with TLX device
    mock_growatt_classic_api.device_list.return_value = [
        {"deviceSn": "TLX123456", "deviceType": "tlx"}
    ]

    mock_config_entry_classic.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry_classic.entry_id)
    await hass.async_block_till_done()

    # Get the device
    device_entry = device_registry.async_get_device(identifiers={(DOMAIN, "TLX123456")})
    assert device_entry is not None

    # Unload the config entry
    await hass.config_entries.async_unload(mock_config_entry_classic.entry_id)
    await hass.async_block_till_done()

    # Test service call with unloaded entry (should skip it in get_min_coordinators)
    with pytest.raises(
        ServiceValidationError, match="No MIN devices with token authentication"
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_time_segment",
            {
                "device_id": device_entry.id,
                "segment_id": 1,
                "start_time": "09:00",
                "end_time": "11:00",
                "batt_mode": "load_first",
                "enabled": True,
            },
            blocking=True,
        )
