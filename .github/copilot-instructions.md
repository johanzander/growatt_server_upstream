# Growatt Server Upstream - AI Coding Agent Instructions

## Project Overview

This is a **Home Assistant custom integration** for Growatt solar inverters. It serves as an upstream testing ground for new features before they're submitted to Home Assistant Core. The integration supports both Classic API (username/password) and V1 API (token-based) authentication.

**Key architectural pattern**: This integration uses Home Assistant's `DataUpdateCoordinator` pattern for polling device data every 5 minutes, with separate coordinators per device (MIN, inverter, storage, TLX, MIX) plus one "total" coordinator for plant-level data.

## Critical Concepts

### Dual API Support Architecture
The integration supports two incompatible Growatt APIs that require different code paths:
- **Classic API**: Username/password auth, uses `growattServer.GrowattApi` class
- **V1 API (OpenAPI)**: Token-based auth, uses `growattServer.OpenApiV1` class

**Pattern**: Check `config_entry.data.get(CONF_AUTH_TYPE)` or `coordinator.api_version` throughout the code. See [coordinator.py](custom_components/growatt_server/coordinator.py#L50-L54) for the version check pattern, and [\_\_init\_\_.py](custom_components/growatt_server/__init__.py#L100-L167) for Classic API migration logic.

### API Throttling & Account Lockout Prevention
**Critical**: Growatt locks accounts after too many login attempts. The integration implements persistent throttling:
- [throttle.py](custom_components/growatt_server/throttle.py) provides `ApiThrottleManager` that saves throttle timestamps to disk (survives HA restarts)
- 5-minute cooldown per API call type (stored in Home Assistant's storage with key `growatt_server.api_throttle`)
- **Never call `api.login()` without checking throttle first** - see the pattern in [\_\_init\_\_.py](custom_components/growatt_server/__init__.py#L173-L195)

### Config Entry Migration Pattern
Version 1.1 migration (lines 61-175 in `__init__.py`) demonstrates a complex migration that:
1. Detects auth type from available credentials
2. Resolves `DEFAULT_PLANT_ID` to actual plant ID via API call
3. Caches the authenticated API instance using `CACHED_API_KEY` pattern
4. Reuses cached session in `async_setup_entry()` to avoid double login

**Pattern**: Use `hass.data[DOMAIN][f"{CACHED_API_KEY}{entry_id}"]` to cache API between migration and setup.

## Development Workflows

### Running Tests
```bash
# Install dependencies
./scripts/setup

# Run all tests with pytest
pytest

# Run specific test file
pytest tests/test_init.py

# Test with coverage
pytest --cov=custom_components.growatt_server
```

**Important**: Tests use `pytest_homeassistant_custom_component` which provides HA test fixtures. Fixtures in [conftest.py](tests/conftest.py) define `mock_growatt_v1_api` and `mock_growatt_classic_api` for API mocking.

### Linting & Formatting
```bash
# Auto-format and fix issues
./scripts/lint

# Uses ruff for both formatting and linting
```

### Local Development with Home Assistant
```bash
# Start HA with custom component loaded
./scripts/develop

# Sets PYTHONPATH to include custom_components/
# Creates config/ directory if needed
# Runs HA in debug mode
```

## Testing Patterns

### Snapshot Testing
This project uses **syrupy** for snapshot testing. See [test_sensor.py](tests/test_sensor.py#L21-L32) for examples:
- Use `snapshot_platform()` helper for entity state snapshots
- Snapshots stored in `tests/snapshots/*.ambr`
- Update snapshots with `pytest --snapshot-update`

### Mocking API Calls
**Pattern from conftest.py**: Mock API methods return dict data, not objects:
```python
mock_api.device_list.return_value = {"data": [...]}
mock_api.min_detail.return_value = {"acChargeEnable": 1, ...}
```

### Throttle Testing
Use `@pytest.mark.no_throttle_mock` marker to disable throttle mocking (see [test_throttle.py](tests/test_throttle.py)). By default, throttle manager is mocked in conftest fixtures.

## File Organization & Naming

- **Sensor entities**: Device-specific sensors split by type in `sensor/` subdirectory ([inverter.py](custom_components/growatt_server/sensor/inverter.py), [mix.py](custom_components/growatt_server/sensor/mix.py), etc.)
- **Entity descriptions**: Use `GrowattSensorEntityDescription` dataclass with `api_key` field to map API response keys to entities
- **Constants**: All in [const.py](custom_components/growatt_server/const.py) - includes auth types, battery modes, error codes, etc.

## Integration-Specific Patterns

### Coordinator Data Structure
`coordinator.data` is a flat dict of API response fields. Example from MIN device:
```python
{"acChargeEnable": 1, "chargePowerCommand": 5000, "pCharge1": 2500, ...}
```

Sensors access via `coordinator.data.get(entity_description.api_key)`.

### Services Architecture
Services in [services.py](custom_components/growatt_server/services.py) support **MIN and SPH devices** with **V1 API-only**:
- `update_time_segment` / `clear_time_segment` / `get_time_segments` for TOU (Time of Use) control
- Device selection uses Home Assistant device registry, not serial numbers
- Helper `get_coordinator(device_id)` maps device_id → serial → coordinator
- MIN uses `min_write_time_segment`
- SPH uses `sph_write_ac_charge_times` (battery-first mode) and `sph_write_ac_discharge_times` (other modes)

### Re-authentication Flow
When API returns auth failure (Classic API: msg=`LOGIN_INVALID_AUTH_CODE`), integration triggers reauth flow. See [config_flow.py](custom_components/growatt_server/config_flow.py#L64-L105) for the `async_step_reauth_confirm` implementation.

## Common Gotchas

1. **Plant ID vs Device ID**: `plant_id` identifies the plant (site), `device_id` is the serial number. The "total" coordinator uses `plant_id`, device coordinators use `device_id`.

2. **API Version Mismatches**: Some features (MIN/SPH control, services) only work with V1 API. Always check `api_version` before accessing V1-specific features.

3. **Coordinator Updates**: Coordinators run every 5 minutes. Don't assume fresh data - use `await coordinator.async_request_refresh()` to force updates when needed.

4. **Entity Availability**: Entities become unavailable if coordinator update fails (raises `UpdateFailed`). The integration remains loaded.

5. **Testing Auth**: When testing authentication flows, remember throttle manager is mocked by default. Use `@pytest.mark.no_throttle_mock` to test throttle behavior.

## Submitting to HA Core

Changes here should be compatible with Home Assistant Core submission requirements:
- Follow HA's code quality standards (enforced by `ruff`)
- Use HA's built-in helpers (`DataUpdateCoordinator`, `ConfigFlow`, entity base classes)
- Add tests for new features with >95% coverage
- Update entity descriptions with proper `device_class`, `state_class` for Energy Dashboard compatibility
