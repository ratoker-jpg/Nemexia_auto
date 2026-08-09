# Nemexia Raid Manager V2

Current production release: **V2 2.0.0 — PySide6 / Qt default**.

## Start

On Windows with Python 3.10 x64 or 3.11 x64:

```text
install.bat
run_app.bat
```

The production path is:

```text
run_app.bat -> app_qt.py -> PySide6 V2
```

The tested rollback path is intentionally retained:

```text
run_legacy.bat -> app_entry.py -> legacy Tkinter
```

Full Russian installation, upgrade, storage and rollback instructions: [`README_RU.md`](README_RU.md).

## Release state

- V2 SQLite schema: **9**.
- V2 runtime storage: `%LOCALAPPDATA%\NemexiaRaidManagerV2\`.
- Legacy SQLite is opened by V2 read-only (`mode=ro`, `PRAGMA query_only=ON`).
- Startup/shutdown V2 backups and restart recovery are release-gated.
- Windows CI validates Python 3.10, Python 3.11, legacy self-test, real PySide6 MainWindow at 1180×720 and 1440×900, real installer, Qt default launcher, existing-user upgrade and legacy fallback.

## Important safety boundary

The Qt release deliberately remains **attach-only**. `NO NAVIGATION BOUNDARY` is still authoritative. This release does not add automatic 3×40 traversal, background page/planet/system navigation, Rest Mode navigation loops, automatic `refreshGalaxy`, V2 `change_planet.php`, arbitrary `page.goto`, CAPTCHA solving/clicking, automatic message deletion, retry after an ambiguous remote side effect, creation of a replacement espionage route when no exact processable spy fleet exists, or an unattended asteroid/debris scheduler.

These are deferred feature contracts, not blockers for the current Qt release.

## Release records

- Current state: [`docs/v2-current-state.md`](docs/v2-current-state.md)
- Release/cutover plan: [`docs/plans/2026-08-09-v2-release-cutover-batch.md`](docs/plans/2026-08-09-v2-release-cutover-batch.md)
- Tk→Qt parity audit: [`docs/audits/2026-08-09-v2-release-cutover-parity-audit.md`](docs/audits/2026-08-09-v2-release-cutover-parity-audit.md)
- Legacy reachability audit: [`docs/audits/2026-08-09-v2-legacy-reachability-audit.md`](docs/audits/2026-08-09-v2-legacy-reachability-audit.md)
- Final release handoff: [`docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md`](docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md)
