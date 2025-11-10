# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core. From version 1.5.0 it should be compatible with the [Growatt BESS (Battery Energy Storage System) Manager][bess]

## Features (v2.2.0)

**Base Version**: Home Assistant Core 2025.9.0 Growatt Server integration

**Changes from Base Version**:

1. `manifest.json` updated for custom component distribution
2. [API Token authentication support][pr-149783] - Official V1 API for MIN/TLX/MIX devices
3. [MIN inverter control][pr-153468] - Number, switch, and time entities for controlling inverter settings
4. **MIX/SPH inverter control** - Full support for charge/discharge power, SOC limits, and time-of-use scheduling
5. Adds 5 min rate limit to login to prevent account locking - aims to fix [account locking issue][issue-150732]
6. **Fixed sensor naming issue** - Sensors now display proper translated names instead of generic device class names
7. **Fixed timezone handling in API throttling** - Fixed bug that could cause very long throttling times (500 minutes)
8. **Enhanced TLX sensor coverage** - Added 14 new sensors for power and energy
monitoring
9. Proper implementation of read / write Time Of Use (TOU) settings using service calls:
  `growattserver.read_time_segments,
  growattserver.update_time_segment`

### MIN/TLX/MIX Inverter Control Features (V1 API)

When using token authentication with MIN/TLX or MIX/SPH inverters, you get:

**Number Entities**:

- Charge power (W)
- Charge stop SOC (%)
- Discharge power (W)
- Discharge stop SOC (%)

**Switch Entities**:

- AC charge enable/disable
- Charge period 1 enabled
- Discharge period 1 enabled

**Time Entities**:

- 1. Charge start time
- 2. Charge end time
- 3. Discharge start time
- 4. Discharge end time

All control entities provide real-time feedback and proper error handling. MIX/SPH devices support full time-of-use (TOU) scheduling with separate charge and discharge periods.

### Enhanced TLX Sensor Coverage (v1.4.6)

Added 14 new sensors for power and energy monitoring:

**Power Flow Monitoring**:

- Solar generation today
- Local load power, import power, export power
- System power, self power

**Energy Accounting**:

- System production (today/total)
- Self-consumption (today/total)
- Grid import/export (today/total)
- Battery charging from grid (today/total)

These sensors provide complete visibility into energy flows and system performance for TLX/MIN inverters.

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

