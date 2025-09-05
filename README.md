# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core.

## Features

- = **Latest Core Features**: Based on latest Home Assistant Core
- >ê **Early Access**: Test upcoming improvements before official release
- = **Bug Fixes**: Get fixes faster than waiting for HA releases
- =á **Stability**: Additional error handling and reliability improvements

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations" 
3. Click the 3-dot menu ’ "Custom repositories"
4. Add repository URL: `https://github.com/johanzander/growatt_server_upstream`
5. Select category: "Integration"
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Download the `custom_components` folder
2. Copy to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

Configure exactly like the standard Growatt Server integration:

1. Go to Settings ’ Devices & Services
2. Click "Add Integration" 
3. Search for "Growatt Server"
4. Follow the configuration steps

**Note**: Remove or disable the core Growatt Server integration first to avoid conflicts.

## Support

- = **Issues**: [GitHub Issues][issues]
- =Ö **Documentation**: [Home Assistant Docs](https://www.home-assistant.io/integrations/growatt_server/)

## Contributing

Contributions are welcome! All contributions will be considered for submission back to Home Assistant Core.

---

[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs]: https://github.com/hacs/integration
[issues]: https://github.com/johanzander/growatt_server_upstream/issues
[releases-shield]: https://img.shields.io/github/release/johanzander/growatt_server_upstream.svg
[releases]: https://github.com/johanzander/growatt_server_upstream/releases