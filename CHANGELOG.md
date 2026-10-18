# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.1.0] - 2026-10-19 - Phase 1 Foundation (signed off)

### Added
- Conda environment `3form_WMS` (Python 3.11, Django 4.2 LTS) via `environment.yml`.
- `config/settings.yaml` holds every tunable value; `config/industries/*.yaml` holds 6 industry presets
  (steps, scrap reasons, downtime reasons, sign-off rule).
- One log file per channel (app, scanner, camera, aps, agent, audit), rotated daily, kept 90 days.
- PostgreSQL 16 for WMS / people / audit trail, and MongoDB Atlas Local on port 27032 for MES events.
  Both run in Docker (`deploy/docker-compose.dev.yml`).
- Unique human-readable IDs, made automatically: `WO-…`, `B-…`, `WIP-B-…-S03-001`, plus a hidden
  event ID on every scan and button press, so nothing is counted twice.
- Roles: PIC > Engineering Manager > Worker, with per-person expiring logins, a 30-minute idle
  logout, and a lock after 5 failed attempts.
- Workers log in with their staff ID only, on PIC-registered devices only (also by badge scan).
- Append-only audit trail. Only the PIC can correct WIP or scrap records, and a reason is required.
- MES basics: work orders (PIC-typed = Special / Urgent), batches, and step Start / Finish / Scrap /
  Machine stopped / Resume / Measure. Scrap is recorded at every step; workers never see scrap totals.
- Site gateway: Honeywell TCP/IP driver (client or server mode), offline outbox, heartbeat.
  `tools/scanner_simulator.py` for testing without hardware.
- Network alarm on the worker screen (red frame, sound, "Fix it" checklist). Worker actions are kept
  on the tablet while offline and sent automatically when the network is back.
- New Vue 3 front end in the 3Form look (Inter + Source Serif 4, EN / 繁中, light and dark, WCAG 2.2 AA
  contrast checked). Pages: Login, Worker station, Progress (production-line rail), Workstations,
  Work Orders, Scrap Trace-back, Stock, Excel Export, People, Devices, Audit Trail, Settings.
- Excel export (7 sheets) by button and `manage.py export_production` (nightly).
- `deploy/backup/backup.sh`: daily PostgreSQL + MongoDB dumps, kept 30 days.
- Light colour theme by default, with a Light / Dark / Auto switch remembered per device.
- 23 automated tests (`pytest`).

### Changed
- Errors from the API now return their real HTTP status (previously always 200).
- Time zone is Asia/Hong_Kong; the default language is English.
- Throttling uses standard per-user / per-IP limits instead of one database write per request.

### Removed
- The old GreaterWMS Vue 2 screens (`templates/`) and the mobile app (`app/`).
- Railway / Render hosting files (`railway.json`, `render.yaml`, `Dockerfile.render`).
- Legacy `/login/` (shared never-expiring token) and `/register/` (open company sign-up) endpoints.

### Security
- Device tokens and login tokens are stored only as SHA-256 hashes.
- CORS is limited to listed origins. Secrets live in `.env` (not committed).

### Data
- The 1,192 legacy SQLite records were copied into PostgreSQL (`backups/legacy_sqlite_dump.json`).
  The old `db.sqlite3` file stays in place as a fallback copy.

---

## [2.1.50] - 2024-XX-XX

### Added
- Example: New inventory management features
- Example: Enhanced user authentication system

### Changed
- Example: Updated API response format for better consistency

### Fixed
- Example: Fixed stock calculation errors in warehouse module
- Example: Resolved UI display issues on mobile devices

### Security
- Example: Updated dependencies to address security vulnerabilities

## [2.1.49] - 2024-XX-XX

### Added
- Example: Multi-language support for French users
- Example: New reporting dashboard

### Fixed
- Example: Fixed database connection timeout issues
- Example: Resolved memory leaks in background processes

---

## Guidelines for Maintaining the Changelog

### When to Update
- **Immediately** when merging PRs that affect users
- **Before each release** to ensure completeness
- **When fixing bugs** that were reported by users

### What to Include
- **User-facing changes**: Features, bug fixes, API changes
- **Security updates**: Vulnerability fixes, dependency updates
- **Breaking changes**: Changes that require user action
- **Performance improvements**: Significant performance gains

### What NOT to Include
- Internal refactoring that doesn't affect users
- CI/CD pipeline changes
- Code formatting or style changes
- Documentation updates (unless they reflect feature changes)

### Writing Guidelines
1. **Use clear, non-technical language** that users can understand
2. **Link to issues/PRs** where relevant: `- Fixed login bug (#123)`
3. **Group related changes** under appropriate categories
4. **Mention breaking changes prominently** in the Changed section
5. **Include migration instructions** for breaking changes

### Categories Explained
- **Added**: New features, APIs, or capabilities
- **Changed**: Modifications to existing features (including breaking changes)
- **Deprecated**: Features marked for removal in future versions
- **Removed**: Features that have been completely removed
- **Fixed**: Bug fixes and error corrections
- **Security**: Security-related fixes and improvements

### Release Process
1. Update the `[Unreleased]` section with new changes
2. Before release, move unreleased changes to a new version section
3. Add release date in YYYY-MM-DD format
4. Create a new empty `[Unreleased]` section
5. Update version links at the bottom if using comparison links

### Example Entry Format
```markdown
## [1.2.3] - 2024-01-15

### Added
- New user dashboard with customizable widgets (#145)
- API endpoint for bulk inventory updates (#156)

### Changed
- **BREAKING**: User authentication now requires email verification (#134)
- Improved performance of stock calculation by 40% (#142)

### Fixed
- Fixed crash when uploading large CSV files (#138)
- Resolved timezone display issues in reports (#149)

### Security
- Updated all dependencies to latest secure versions (#151)
```

### Semantic Versioning Guidelines
- **MAJOR** (X.0.0): Breaking changes that require user action
- **MINOR** (1.X.0): New features that are backwards compatible
- **PATCH** (1.1.X): Bug fixes and small improvements

### Automation
This project uses [release-drafter](https://github.com/release-drafter/release-drafter) to automatically generate release notes from merged PRs. The changelog should be updated manually to ensure accuracy and user-friendly language.