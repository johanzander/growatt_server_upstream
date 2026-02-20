"""Common fixtures for the Growatt server tests."""

from unittest.mock import Mock, patch

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.growatt_server.const import (
    AUTH_API_TOKEN,
    AUTH_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_PLANT_ID,
    DEFAULT_PLANT_ID,
    DEFAULT_URL,
    DOMAIN,
)
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return snapshot assertion fixture with the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def mock_growatt_v1_api():
    """Return a mocked Growatt V1 API.

    This fixture provides the happy path for integration setup and basic operations.
    Individual tests can override specific return values to test error conditions.

    Methods mocked for integration setup:
    - device_list: Called during async_setup_entry to discover devices
    - plant_energy_overview: Called by total coordinator during first refresh

    Methods mocked for MIN device coordinator refresh:
    - min_detail: Provides device state (e.g., acChargeEnable, chargePowerCommand)
    - min_settings: Provides settings (e.g. TOU periods)
    - min_energy: Provides energy data (empty for switch/number tests, sensors need real data)

    Methods mocked for SPH device coordinator refresh:
    - sph_detail: Provides device state (similar to min_detail)
    - sph_energy: Provides energy data (similar to min_energy)

    Methods mocked for switch and number operations:
    - min_write_parameter: Called by switch/number entities to change MIN settings
    - sph_write_parameter: Called by switch/number entities to change SPH settings

    Methods mocked for service operations:
    - min_write_time_segment: Called by time segment management services for MIN
    - sph_write_ac_charge_times: Called by time segment services for SPH charge mode
    - sph_write_ac_discharge_times: Called by time segment services for SPH discharge modes
    """
    with patch(
        "homeassistant.components.growatt_server.config_flow.growattServer.OpenApiV1",
        autospec=True,
    ) as mock_v1_api_class:
        mock_v1_api = mock_v1_api_class.return_value

        # Called during setup to discover devices
        mock_v1_api.device_list.return_value = {
            "devices": [
                {
                    "device_sn": "MIN123456",
                    "type": 7,  # MIN device type
                }
            ]
        }

        # Called by MIN device coordinator during refresh
        mock_v1_api.min_detail.return_value = {
            "deviceSn": "MIN123456",
            "acChargeEnable": 1,  # AC charge enabled - read by switch entity
            "chargePowerCommand": 50,  # 50% charge power - read by number entity
            "wchargeSOCLowLimit": 10,  # 10% charge stop SOC - read by number entity
            "disChargePowerCommand": 80,  # 80% discharge power - read by number entity
            "wdisChargeSOCLowLimit": 20,  # 20% discharge stop SOC - read by number entity
        }

        # Called by MIN device coordinator during refresh
        mock_v1_api.min_settings.return_value = {
            # Time segment 1 - enabled, load_first mode
            "forcedTimeStart1": "06:00",
            "forcedTimeStop1": "08:00",
            "time1Mode": 1,  # load_first
            "forcedStopSwitch1": 1,  # enabled
            # Time segment 2 - disabled
            "forcedTimeStart2": "22:00",
            "forcedTimeStop2": "24:00",
            "time2Mode": 0,  # battery_first
            "forcedStopSwitch2": 0,  # disabled
            # Time segments 3-9 - all disabled with default values
            "forcedTimeStart3": "00:00",
            "forcedTimeStop3": "00:00",
            "time3Mode": 1,
            "forcedStopSwitch3": 0,
            "forcedTimeStart4": "00:00",
            "forcedTimeStop4": "00:00",
            "time4Mode": 1,
            "forcedStopSwitch4": 0,
            "forcedTimeStart5": "00:00",
            "forcedTimeStop5": "00:00",
            "time5Mode": 1,
            "forcedStopSwitch5": 0,
            "forcedTimeStart6": "00:00",
            "forcedTimeStop6": "00:00",
            "time6Mode": 1,
            "forcedStopSwitch6": 0,
            "forcedTimeStart7": "00:00",
            "forcedTimeStop7": "00:00",
            "time7Mode": 1,
            "forcedStopSwitch7": 0,
            "forcedTimeStart8": "00:00",
            "forcedTimeStop8": "00:00",
            "time8Mode": 1,
            "forcedStopSwitch8": 0,
            "forcedTimeStart9": "00:00",
            "forcedTimeStop9": "00:00",
            "time9Mode": 1,
            "forcedStopSwitch9": 0,
        }

        # Called by MIN device coordinator during refresh
        # Provide realistic energy data for sensor tests
        mock_v1_api.min_energy.return_value = {
            "eChargeToday": 5.2,
            "eChargeTotal": 125.8,
            "eDischargeToday": 8.1,
            "eDischargeTotal": 245.6,
            "eSelfToday": 12.5,
            "eSelfTotal": 320.4,
            "eBatChargeToday": 6.3,
            "eBatChargeTotal": 150.2,
            "eBatDischargeToday": 7.8,
            "eBatDischargeTotal": 180.5,
        }

        # Called by total coordinator during refresh
        mock_v1_api.plant_energy_overview.return_value = {
            "today_energy": 12.5,
            "total_energy": 1250.0,
            "current_power": 2500,
        }

        # Called by switch/number entities during turn_on/turn_off/set_value
        mock_v1_api.min_write_parameter.return_value = None
        mock_v1_api.sph_write_parameter.return_value = None

        # Called by time segment management services
        # Note: Don't use autospec for this method as it needs to accept variable arguments
        mock_v1_api.min_write_time_segment = Mock(
            return_value={
                "error_code": 0,
                "error_msg": "Success",
            }
        )
        # SPH uses separate methods for charge and discharge times
        mock_v1_api.sph_write_ac_charge_times = Mock(
            return_value={
                "error_code": 0,
                "error_msg": "Success",
            }
        )
        mock_v1_api.sph_write_ac_discharge_times = Mock(
            return_value={
                "error_code": 0,
                "error_msg": "Success",
            }
        )

        # Called by SPH device coordinator during refresh
        # Provide similar data structure to MIN but for SPH devices
        mock_v1_api.sph_detail.return_value = {
            "deviceSn": "SPH123456",
            "acChargeEnable": 1,  # AC charge enabled - read by switch entity
            "chargePowerCommand": 50,  # 50% charge power - read by number entity
            "wchargeSOCLowLimit": 10,  # 10% charge stop SOC - read by number entity
            "disChargePowerCommand": 80,  # 80% discharge power - read by number entity
            "wdisChargeSOCLowLimit": 20,  # 20% discharge stop SOC - read by number entity
            # Include time segment settings directly in sph_detail (SPH doesn't have separate settings API)
            "forcedTimeStart1": "06:00",
            "forcedTimeStop1": "08:00",
            "time1Mode": 1,
            "forcedStopSwitch1": 1,
            "forcedTimeStart2": "22:00",
            "forcedTimeStop2": "24:00",
            "time2Mode": 0,
            "forcedStopSwitch2": 0,
            "forcedTimeStart3": "00:00",
            "forcedTimeStop3": "00:00",
            "time3Mode": 1,
            "forcedStopSwitch3": 0,
            "forcedTimeStart4": "00:00",
            "forcedTimeStop4": "00:00",
            "time4Mode": 1,
            "forcedStopSwitch4": 0,
            "forcedTimeStart5": "00:00",
            "forcedTimeStop5": "00:00",
            "time5Mode": 1,
            "forcedStopSwitch5": 0,
            "forcedTimeStart6": "00:00",
            "forcedTimeStop6": "00:00",
            "time6Mode": 1,
            "forcedStopSwitch6": 0,
            "forcedTimeStart7": "00:00",
            "forcedTimeStop7": "00:00",
            "time7Mode": 1,
            "forcedStopSwitch7": 0,
            "forcedTimeStart8": "00:00",
            "forcedTimeStop8": "00:00",
            "time8Mode": 1,
            "forcedStopSwitch8": 0,
            "forcedTimeStart9": "00:00",
            "forcedTimeStop9": "00:00",
            "time9Mode": 1,
            "forcedStopSwitch9": 0,
        }

        mock_v1_api.sph_energy.return_value = {
            "eChargeToday": 5.2,
            "eChargeTotal": 125.8,
            "eDischargeToday": 8.1,
            "eDischargeTotal": 245.6,
            "eSelfToday": 12.5,
            "eSelfTotal": 320.4,
            "eBatChargeToday": 6.3,
            "eBatChargeTotal": 150.2,
            "eBatDischargeToday": 7.8,
            "eBatDischargeTotal": 180.5,
        }

        yield mock_v1_api


@pytest.fixture
def mock_growatt_classic_api():
    """Return a mocked Growatt Classic API.

    This fixture provides the happy path for Classic API integration setup.
    Individual tests can override specific return values to test error conditions.

    Methods mocked for integration setup:
    - login: Called during get_device_list_classic to authenticate
    - plant_list: Called during setup if plant_id is default (to auto-select plant)
    - device_list: Called during async_setup_entry to discover devices

    Methods mocked for total coordinator refresh:
    - plant_info: Provides plant totals (energy, power, money) for Classic API

    Methods mocked for device coordinators (individual device data):
    - inverter_detail: Provides inverter device data
    - storage_detail: Provides storage device data
    - mix_detail: Provides mix device data
    - tlx_detail: Provides TLX device data
    """
    with patch(
        "homeassistant.components.growatt_server.config_flow.growattServer.GrowattApi",
        autospec=True,
    ) as mock_classic_api_class:
        # Use the autospec'd mock instance instead of creating a new Mock()
        mock_classic_api = mock_classic_api_class.return_value

        # Called during setup to authenticate with Classic API
        mock_classic_api.login.return_value = {"success": True, "user": {"id": 12345}}

        # Called during setup if plant_id is default (auto-select first plant)
        mock_classic_api.plant_list.return_value = {"data": [{"plantId": "12345"}]}

        # Called during setup to discover devices
        # Default to empty list - individual tests should override with specific devices
        mock_classic_api.device_list.return_value = []

        # Called by total coordinator during refresh for Classic API
        mock_classic_api.plant_info.return_value = {
            "deviceList": [],
            "totalEnergy": 1250.0,
            "todayEnergy": 12.5,
            "invTodayPpv": 2500,
            "plantMoneyText": "123.45/USD",
        }

        # Called by device coordinators during refresh for various device types
        mock_classic_api.inverter_detail.return_value = {
            "deviceSn": "INV123456",
            "status": 1,
        }

        mock_classic_api.storage_detail.return_value = {
            "deviceSn": "STO123456",
        }

        mock_classic_api.mix_detail.return_value = {
            "deviceSn": "MIX123456",
            "chartData": {"06:00": {}},  # At least one time entry needed
        }

        mock_classic_api.tlx_detail.return_value = {
            "data": {
                "deviceSn": "TLX123456",
            }
        }

        yield mock_classic_api


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry (V1 API with token auth).

    This is the primary config entry used by most tests. For Classic API tests,
    use mock_config_entry_classic instead.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_API_TOKEN,
            CONF_TOKEN: "test_token_123",
            CONF_URL: DEFAULT_URL,
            "user_id": "12345",
            CONF_PLANT_ID: "123456",
            "name": "Test Plant",
        },
        unique_id="123456",
    )


@pytest.fixture
def mock_config_entry_classic() -> MockConfigEntry:
    """Return a mocked config entry for Classic API (password auth).

    Use this for tests that specifically need to test Classic API behavior.
    Most tests use the default mock_config_entry (V1 API) instead.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_PASSWORD,
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_password",
            CONF_URL: DEFAULT_URL,
            CONF_PLANT_ID: "123456",
            "name": "Test Plant",
        },
        unique_id="123456",
    )


@pytest.fixture
def mock_config_entry_classic_default_plant() -> MockConfigEntry:
    """Return a mocked config entry for Classic API with DEFAULT_PLANT_ID.

    This config entry uses plant_id="0" which triggers auto-plant-selection logic
    in the Classic API path. This is legacy support for old config entries that
    didn't have a specific plant_id set during initial configuration.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_TYPE: AUTH_PASSWORD,
            CONF_USERNAME: "test_user",
            CONF_PASSWORD: "test_password",
            CONF_URL: "https://server.growatt.com/",
            CONF_PLANT_ID: DEFAULT_PLANT_ID,  # "0" triggers auto-selection
            "name": "Test Plant",
        },
        unique_id="plant_default",
        minor_version=0,  # triggers migration, where DEFAULT_PLANT_ID resolution now lives
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_growatt_v1_api
) -> MockConfigEntry:
    """Set up the Growatt Server integration for testing (V1 API).

    This combines mock_config_entry and mock_growatt_v1_api to provide a fully
    initialized integration ready for testing. Use @pytest.mark.usefixtures("init_integration")
    to automatically set up the integration before your test runs.

    For Classic API tests, manually set up using mock_config_entry_classic and
    mock_growatt_classic_api instead.
    """
    # The mock_growatt_v1_api fixture is required for patches to be active
    assert mock_growatt_v1_api is not None

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry to prevent actual setup during config flow tests."""
    with patch(
        "homeassistant.components.growatt_server.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_throttle_manager(request):
    """Mock the throttle manager to always allow API calls during tests.

    This fixture is autouse=True so it applies to all tests automatically,
    except for tests marked with @pytest.mark.no_throttle_mock.
    The throttle manager will never block API calls during testing.
    """
    # Skip mocking for tests that need real throttle behavior
    if "no_throttle_mock" in request.keywords:
        yield None
        return

    with (
        patch(
            "custom_components.growatt_server.throttle.ApiThrottleManager.should_throttle",
            return_value=False,  # Never throttle during tests
        ),
        patch(
            "custom_components.growatt_server.throttle.ApiThrottleManager.throttled_call"
        ) as mock_throttled_call,
    ):
        # Make throttled_call pass through to the actual function
        async def passthrough_call(func, *args, **kwargs):
            """Execute the function without throttling."""
            import asyncio

            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        mock_throttled_call.side_effect = passthrough_call
        yield mock_throttled_call
