# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core.

## Features (v1.3.2)

**Base Version**: Home Assistant Core 2025.9.0 Growatt Server integration  

**Changes from Base Version**:

1. `manifest.json` updated for custom component distribution
2. [API Token authentication support][pr-149783] - Official V1 API for MIN devices
3. [Improved error handling during login][pr-151025]
4. Adds 5 min rate limit to login to prevent account locking - aims to fix [account locking issue][issue-150732]

## Installation

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
12. Search for "Growatt Server"
13. Follow the configuration steps

### Manual Installation

1. Download the `custom_components` folder
2. Copy to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

Configure exactly like the standard Growatt Server integration:

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Growatt Server"
4. Follow the configuration steps

**Note**: Remove or disable the core Growatt Server integration first to avoid conflicts.

## Contributing

Contributions welcome! Create feature branch, implement changes, test thoroughly, submit PR. All contributions considered for submission back to Home Assistant Core.

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
[pr-151025]: https://github.com/home-assistant/core/pull/151025
[issue-150732]: https://github.com/home-assistant/core/issues/150732
