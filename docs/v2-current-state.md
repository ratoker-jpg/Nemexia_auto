# Nemexia Raid Manager V2 — current state

Updated by V2-30 after the #52–#60 migration batch. Baseline entering V2-30: `610eb763c7cf4a3b05cc0d3f3f41122936c6fc75`.

## Safety baseline

The pre-PySide6 working version remains recoverable at:

- `stable/tkinter-v1`
- `archive/pre-pyside6-4e01bfda`
- source SHA `4e01bfda752c6383e48c0f6eb8be64d68676da67`

The default launcher is still `run_app.bat -> app_entry.py` (Tkinter). V2 remains a separate `app_qt.py` entrypoint.

## V2 storage boundary

Legacy data source:

- opened through SQLite `mode=ro`;
- `PRAGMA query_only=ON`;
- targets/history/queue/recon and allow-listed migration inputs are reads only.

V2-owned data:

- `%LOCALAPPDATA%/NemexiaRaidManagerV2/`;
- versioned SQLite with `PRAGMA user_version`;
- typed allow-listed settings only;
- atomic settings batches;
- SQLite-native consistent backups with retention.

Only these legacy settings are eligible for first-run import, and only when the corresponding V2 key is still absent:

- `port` -> `cdp_port`;
- `home_g/home_s/home_p` -> `farm_home`;
- `farm_return_buffer_minutes` -> same V2 key.

## Live browser boundary

V2 attaches to an existing Chromium/Yandex CDP session and reads an already-open `fleets.php` page. It does not navigate or create tabs.

Verified read facts include:

- `#fleetHandler tbody tr`;
- `#FleetsCount`;
- `#MaxFleets`;
- `#planetsListHolder a`.

CAPTCHA remains fail-closed. No CAPTCHA solving/clicking exists.

## Flight semantics

V2 has typed classification for:

- outgoing / incoming / foreign;
- personal / command / unknown ownership;
- excluded flights;
- exact normal `Атака`;
- farm-cycle-blocking flights.

Current policy:

- command planet default `2:5:6` is centralized and editable in V2 settings;
- command involvement excludes a flight from personal calculations;
- physical fleet capacity comes from game `FleetsCount/MaxFleets`, never `len(flights)`;
- only an exact outbound `Атака` from configured `farm_home` blocks the farm timer;
- recycling/transport/etc. may occupy game capacity but do not drive the farm return timer;
- live Overview uses latest blocking return + configured buffer and compares it with persisted legacy `farm_next_cycle_at` read-only.

## Real Qt pages

Currently backed by real services/data:

- Overview;
- Plan (read-only persisted queue);
- Active (explicit live refresh + typed classification + capacity);
- Recon (read-only saved spy reports);
- Targets;
- History;
- Settings (V2-owned settings only);
- Diagnostics.

Still placeholders / not migrated:

- Auto-farm;
- Asteroids;
- Debris.

## Explicitly not enabled yet

V2 still exposes no UI/application API for:

- raid dispatch;
- fleet form filling;
- spy requests;
- message deletion;
- queue mutation;
- automatic browser navigation;
- auto-farm execution;
- asteroid/debris execution.

## Verification gate

GitHub Actions currently runs on Windows:

- Python 3.10: compileall + pytest + legacy self-test;
- Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

The local working installation should not be updated to V2 until action parity and final cutover are explicitly completed.
