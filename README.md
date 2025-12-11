# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core. From version 1.5.0 it should be compatible with the [Growatt BESS (Battery Energy Storage System) Manager][bess]

## Features (v2.0.0)

**Base Version**: Home Assistant Core (latest core/dev branch as of November 3rd 2024)

**New Features in v2.0.0**:

1. **GraemeDBlue Library Integration** - Uses enhanced PyPi_GrowattServer library with improved API handling
2. **Advanced Rate Limiting** - 5-minute API throttling with automatic retry and user notifications
3. **Time-of-Use (TOU) Services** - Complete service implementation for MIN/MIX device battery management:
   - `growatt_server.read_time_segments` - Read current TOU settings
   - `growatt_server.update_time_segment` - Update individual time segments
4. **Enhanced Error Handling** - Persistent notifications during API throttling periods

### Time-of-Use (TOU) Services (v2.0.0)

**Available Services**:

- `growatt_server.read_time_segments` - Read current TOU settings from device
- `growatt_server.update_time_segment` - Update individual time segment settings

**Battery Operation Modes** (used in time segments):

- `load_first` - Prioritize local load consumption
- `battery_first` - Prioritize battery charging  
- `grid_first` - Prioritize grid power usage

**Example Service Calls**:

```yaml
# Read current TOU settings
service: growatt_server.read_time_segments
target:
  device_id: your_device_id

# Update time segment 1 (08:00-12:00) to battery first mode
service: growatt_server.update_time_segment
target:
  device_id: your_device_id
data:
  segment_id: 1
  batt_mode: "battery_first"
  start_time: "08:00"
  end_time: "12:00"
  enabled: true
```

## Installation

**Note**: Remove the core Growatt Server integration first to avoid conflicts.

### HACS (Recommended)

#### Step 1: Add Custom Repository

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the 3-dot menu → "Custom repositories"
4. Add repository URL: `https://github.com/johanzander/growatt_server_upstream`
5. Select category: "Integration"
6. Click "Add"

#### Step 2: Download the Integration

1. Search for "Growatt Server Upstream" in HACS
2. Click on it and select "Download"
3. Restart Home Assistant

#### Step 3: Configure the Integration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Growatt Server Upstream"
4. Follow the configuration steps

### Manual Installation

1. Download the `custom_components` folder
2. Copy to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Rate Limiting Protection

v2.0.0 includes intelligent API rate limiting to prevent account lockouts:

- **5-minute throttling** between API calls that could trigger account locks
- **Automatic retry** - Home Assistant will retry automatically when safe
- **User notifications** - Persistent notifications show countdown timer during throttling
- **Timezone-aware** - Throttle state persists correctly across HA restarts
- **No manual intervention** - Setup continues automatically after throttle period

When throttled, you'll see a notification like:

> 🛡️ **Growatt API Rate Limited - Auto-retry in 3m 45s**
>
> Setup will continue automatically - no restart needed.

## Contributing

Contributions welcome! Create feature branch, implement changes, test thoroughly, submit PR. All contributions considered for submission back to Home Assistant Core.

## Debug Logging

To enable debug logging for troubleshooting issues, add the following to your Home Assistant `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.growatt_server: debug
```

After adding this configuration:

1. Restart Home Assistant
2. Reproduce the issue
3. Check the logs in **Settings → System → Logs** or in your `home-assistant.log` file
4. Include relevant log entries when reporting issues

## Support

- 🐛 **Issues**: [GitHub Issues][issues]
- 📖 **Documentation**: [Home Assistant Docs](https://www.home-assistant.io/integrations/growatt_server/)

---

[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs]: https://github.com/hacs/integration
[issues]: https://github.com/johanzander/growatt_server_upstream/issues
[releases-shield]: https://img.shields.io/github/release/johanzander/growatt_server_upstream.svg
[releases]: https://github.com/johanzander/growatt_server_upstream/releases
[bess]: https://github.com/johanzander/bess-manager

