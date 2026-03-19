# Growatt Server Upstream

[![GitHub Release][releases-shield]][releases]
[![hacs][hacsbadge]][hacs]

Upstream development version of the Growatt Server integration for Home Assistant.

## About

This repository serves as an **upstream testing ground** for improvements to the Growatt Server integration before they are submitted to Home Assistant Core. From version 1.5.0 it should be compatible with the [Growatt BESS (Battery Energy Storage System) Manager][bess].

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

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

## Troubleshooting

### "Device is already configured" error

If you see this error when trying to add the integration, it means a config entry with the same plant ID already exists. This commonly happens if you previously had the built-in Home Assistant Growatt Server integration configured — even if you removed it from the UI, a stale entry can remain in the config storage.

**To check for a stale entry**, create a [Long-Lived Access Token](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token) from your HA profile, then run:

```bash
curl -s \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://YOUR_HA_ADDRESS:8123/api/config/config_entries/entry \
  | python3 -m json.tool | grep -B 5 -A 10 growatt_server
```

If a stale entry is found, **delete it** using the `entry_id` from the output:

```bash
curl -X DELETE \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://YOUR_HA_ADDRESS:8123/api/config/config_entries/entry/THE_ENTRY_ID
```

Alternatively, you can inspect the file directly via the **File Editor** or **Terminal & SSH** add-ons:

```bash
grep -i growatt /config/.storage/core.config_entries
```

After removing the stale entry, try adding the integration again.

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
