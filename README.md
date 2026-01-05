# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core. From version 1.5.0 it should be compatible with the [Growatt BESS (Battery Energy Storage System) Manager][bess]

## Features

**Current Version**: v2.0.0
**Base Version**: Home Assistant Core 2025.9.0 Growatt Server integration

## What's New in v2.0.0

1. **HA Core Base**: Integration fully based on HA Core version 2026.1
   - includes API Token authentication ([PR #149783][pr-149783])
   - MIN inverter control ([PR #153468][pr-153468])
   - Energy Dashboard support with `state_class`
   - TOU control services, previously only available in upstream v1.6.0
   - Enhanced TLX sensor coverage (14 additional sensors for power/energy monitoring)

2. **Config entry migration**: Seamless upgrade path from older versions - automatically migrates legacy configurations and resolves deprecated plant ID settings (based on [PR #159972](https://github.com/home-assistant/core/pull/159972))
3. **Re-authentication flow**: Detects authentication failures and prompts users to re-enter credentials - prevents silent integration failures by guiding users through credential updates
4. **API caching**: Prevents duplicate login during migration - caches authenticated sessions between migration and setup to avoid triggering account lockout (part of fix for [issue #154724](https://github.com/home-assistant/core/issues/154724))

## Kept from v1.6.0

**Persistent API throttling**: 5-minute cooldown protection that survives Home Assistant restarts - prevents account lockout from too many login attempts even after system reboots (fixes [issue #154724](https://github.com/home-assistant/core/issues/154724))

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

