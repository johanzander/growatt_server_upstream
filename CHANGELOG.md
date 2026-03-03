# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.2] - 2026-03-03

### Fixed
- Restore SPH sensor entities — `sensor/__init__.py` was missing the SPH
  import and device-type branch, so SPH devices had no sensor entities at all
- Restore SPH AC charge/discharge time services — `services.py` was missing
  the refactored `get_coordinator(device_id, device_type)` helper, all four
  SPH service handlers, and their service registrations
- Restore SPH service UI definitions in `translations/en.json`; also update
  "MIN/TLX" references to "MIN/SPH" throughout the config flow
- All of the above were silently dropped by git auto-merge when
  `feature/sph-sensors` was merged into master (files had no conflict markers
  because earlier reverts on master made git treat the deletions as intentional)

## [2.4.1] - 2026-03-03

### Fixed
- SPH (type 5) devices were skipped with "not supported in Open API V1" —
  `V1_DEVICE_TYPES = {5: "sph", 7: "min"}` and related device-list logic were
  lost in the same auto-merge as 2.4.2 fixes

## [2.4.0] - 2026-03-02

### Added
- SPH (Single Phase Hybrid) inverter support via Open API V1
  - 28 dedicated sensor entities using correct `sph_detail` / `sph_energy`
    field names (replaces the Classic API MIX field names that silently
    returned `None` for V1 users)
  - `write_ac_charge_times` service — set all three charge time periods,
    charge power %, charge stop SOC %, and mains-enabled flag in one call
  - `write_ac_discharge_times` service — set all three discharge time periods,
    discharge power %, and discharge stop SOC %
  - `read_ac_charge_times` service — read current charge settings from cache
  - `read_ac_discharge_times` service — read current discharge settings from cache

### Changed
- `get_coordinator()` in `services.py` now accepts a `device_type` parameter,
  making it reusable for both MIN and SPH service actions
- Coordinator cache pattern documented in `GrowattCoordinator` class docstring:
  reads serve from `self.data`, writes update the cache immediately after a
  successful API call — avoids extra calls that would breach the per-endpoint
  5-minute rate limit

### Fixed
- `mix_battery_charge` sensor for SPH: use `pcharge1` (W) instead of
  `bdc1ChargePower` (kW)

## [2.1.1] - 2026-02-23

### Fixed
- Automatic re-login on daily session expiry for Classic API users — the
  Growatt server expires session cookies daily, previously causing all entities
  to become unavailable until Home Assistant was restarted. The coordinator now
  detects the expiry (JSON decode error on HTML login page response) and
  re-authenticates automatically. Uses a shared lock to prevent simultaneous
  logins and a 60-second cooldown to avoid redundant attempts.
  (Thanks @bobaoapae, PR #13)

## [2.1.0] - 2026-02-08

### Changed
- Bump `growattServer` library to 1.9.0

### Fixed
- Midnight bounce suppression for `TOTAL_INCREASING` sensors — resolves Energy
  Dashboard double-counting when the Growatt API delivers stale yesterday values
  immediately after midnight reset ([#162378](https://github.com/home-assistant/core/issues/162378))

## [2.0.0] - 2026-01-05

### Added
- Full rebase onto Home Assistant Core 2026.1 Growatt Server integration,
  including:
  - API Token authentication ([PR #149783](https://github.com/home-assistant/core/pull/149783))
  - MIN inverter control ([PR #153468](https://github.com/home-assistant/core/pull/153468))
  - Energy Dashboard support (`state_class`)
  - TOU control services (previously upstream-only in v1.6.0)
  - Enhanced TLX sensor coverage (14 additional sensors)
- Config entry migration — seamlessly upgrades legacy configurations and
  resolves deprecated plant ID settings
  ([PR #159972](https://github.com/home-assistant/core/pull/159972))
- Re-authentication flow — detects auth failures and prompts users to update
  credentials instead of failing silently
- API session caching — prevents duplicate login during migration to avoid
  triggering account lockout
  ([#154724](https://github.com/home-assistant/core/issues/154724))

### Kept from v1.6.0
- Persistent API throttling — 5-minute cooldown that survives restarts,
  preventing account lockout from excessive login attempts
  ([#154724](https://github.com/home-assistant/core/issues/154724))

[Unreleased]: https://github.com/johanzander/growatt_server_upstream/compare/v2.4.2...HEAD
[2.4.2]: https://github.com/johanzander/growatt_server_upstream/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/johanzander/growatt_server_upstream/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/johanzander/growatt_server_upstream/compare/v2.1.1...v2.4.0
[2.1.1]: https://github.com/johanzander/growatt_server_upstream/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/johanzander/growatt_server_upstream/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/johanzander/growatt_server_upstream/releases/tag/v2.0.0
