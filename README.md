# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core. From version 1.5.0 it should be compatible with the [Growatt BESS (Battery Energy Storage System) Manager][bess]

## Features

**Current Version**: v1.6.0
**Base Version**: Home Assistant Core 2025.9.0 Growatt Server integration

**All Changes from Base Version**:

1. `manifest.json` updated for custom component distribution
2. [API Token authentication support][pr-149783] - Official V1 API for MIN/TLX devices
3. [MIN inverter control][pr-153468] - Number and switch entities for controlling inverter settings
4. **Rate limiting** - 5-minute throttle on API login to prevent account locking (fixes [issue #150732][issue-150732])
5. **Fixed sensor naming** - Sensors now display proper translated names instead of generic device class names
6. **Fixed timezone handling** - Corrected API throttling timezone bug that could cause excessive wait times
7. **Enhanced TLX sensor coverage** - 14 new sensors for power and energy monitoring
8. **Time of Use (TOU) control** - Service calls for reading/updating TOU settings: `growattserver.read_time_segments`, `growattserver.update_time_segment`
9. **Energy Dashboard support** - Added state_class to all power and energy sensors for full Energy dashboard integration

## What's New in v1.6.0

- **Energy Dashboard Integration**: Added `state_class` attributes to 34 power and energy sensors (9 power + 10 energy in MIX, 15 power in TLX), enabling proper integration with Home Assistant's Energy dashboard for tracking solar generation, consumption, and grid import/export

### MIN/TLX Inverter Control (V1 API)

When using token authentication with MIN/TLX inverters:

**Number Entities** (0-100%):
- Charge power / Charge stop SOC
- Discharge power / Discharge stop SOC

**Switch Entities**:
- AC charge enable/disable

All control entities provide real-time feedback and proper error handling.

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

7. Search for "Growatt Server Upstream" in HACS
8. Click on it and select "Download"
9. Restart Home Assistant

#### Step 3: Configure the Integration

10. Go to Settings → Devices & Services
11. Click "Add Integration"
12. Search for "Growatt Server Upstream"
13. Follow the configuration steps

### Manual Installation

1. Download the `custom_components` folder
2. Copy to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

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
[pr-149783]: https://github.com/home-assistant/core/pull/149783
[pr-153468]: https://github.com/home-assistant/core/pull/153468
[issue-150732]: https://github.com/home-assistant/core/issues/150732
[bess]: https://github.com/johanzander/bess-manager

