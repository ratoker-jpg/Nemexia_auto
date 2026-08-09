# Nemexia Raid Manager V2 — final release audit

Date: 2026-08-09  
Audit baseline: `2a21fbc9d97de39fabb2bf658f700b3d57851980` / REL-09  
REL-10 exact squash: `adf1c8318a1a0ffbe79cec2ffd23200cbbc375b5` / PR #125  
REL-10 exact post-merge push-CI: **#287 green**  
Release: V2 2.0.0

## Audit conclusion

The repository passed the final Qt-default release gate. REL-10 completed with all four CI jobs green on the exact squash SHA and no unresolved substantive P1/P2.

No new gameplay/browser capability was required or added for release. No legacy production deletion was authorized.

## Repository truth checked

- `run_app.bat` invokes `app_qt.py` and not `app_entry.py`.
- `run_legacy.bat` invokes `app_entry.py` and not `app_qt.py`.
- `NemexiaRaidManager.spec` packages `app_qt.py` as `NemexiaRaidManager`.
- `NemexiaRaidManagerLegacy.spec` packages `app_entry.py` as `NemexiaRaidManagerLegacy`.
- `install.bat` prepares the shared Qt+legacy `.venv` and runs the legacy self-test.
- release CI includes the real installer, side-by-side upgrade, default Qt launcher and explicit legacy fallback smokes.
- V2 production lifecycle owns startup/shutdown backup and deterministic close/restart recovery.
- V2 SQLite schema remains 9.
- V2 legacy store remains read-only (`mode=ro`, `PRAGMA query_only=ON`).
- Qt UI gate covers all 11 routes at 1180×720 and 1440×900.
- REL-08 classified `D. PROVEN DEAD = ∅`.
- REL-09 retained the rollback stack with zero production deletions.

## Exact release gate

REL-10 squash:

```text
adf1c8318a1a0ffbe79cec2ffd23200cbbc375b5
```

Exact push-CI **#287** passed:

- Windows Python 3.10 — compileall + full pytest + legacy self-test;
- Windows Python 3.11 — compileall + full pytest + legacy self-test;
- PySide6 Python 3.11 — real QApplication/MainWindow, all 11 routes, 1180×720 + 1440×900;
- Windows clean install + existing-user upgrade — real installer, side-by-side smoke, Qt default launcher and explicit legacy fallback smoke.

## Rollback refs checked

Both repository refs exist and remain unchanged:

```text
stable/tkinter-v1 -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
archive/pre-pyside6-4e01bfda -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
```

## Release blockers

No identified release/cutover blocker remains open:

- production V2 backup/restart lifecycle — green;
- Windows Qt dependency/package path — green;
- clean install and existing-user upgrade — green;
- explicit rollback — green;
- default Qt cutover — complete;
- post-cutover black-box regression — green;
- cleanup reachability — audited;
- rollback retention — hardened;
- final release docs/current-state/install/upgrade/rollback handoff — complete.

## Deliberate limitations

These remain intentional and do not block V2 2.0.0:

- `NO NAVIGATION BOUNDARY`;
- automatic 3×40 traversal absent;
- background browser navigation absent;
- Rest Mode navigation loops absent;
- automatic `refreshGalaxy` absent;
- V2 `change_planet.php` absent;
- arbitrary V2 `page.goto` absent;
- CAPTCHA solve/click/bypass absent;
- automatic message deletion absent;
- automatic retry after ambiguous remote side effect absent;
- no replacement espionage route without exact processable Spy fleet;
- no unattended asteroid/debris scheduler;
- V2-68/V2-69/V2-70 remain not started.

## Final handoff rule

This tiny exact-SHA handoff changes documentation/contracts only. It must pass the same CI/review discipline and exact post-merge push-CI. Once green, the release/cutover batch is closed and development stops until a separate user-directed batch begins.
