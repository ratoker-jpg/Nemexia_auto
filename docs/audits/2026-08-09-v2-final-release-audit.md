# Nemexia Raid Manager V2 — final release audit

Date: 2026-08-09  
Audit baseline: `2a21fbc9d97de39fabb2bf658f700b3d57851980` / REL-09  
Release: V2 2.0.0

## Audit conclusion

The repository is ready for the final Qt-default release handoff subject to REL-10 PR CI/review and exact post-merge push-CI.

No new gameplay/browser capability is required for release. No legacy production deletion is authorized.

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

## Rollback refs checked

Both repository refs exist and remain unchanged:

```text
stable/tkinter-v1 -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
archive/pre-pyside6-4e01bfda -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
```

## Release blockers

No previously identified cutover blocker remains open after REL-09:

- production V2 backup/restart lifecycle — green;
- Windows Qt dependency/package path — green;
- clean install and existing-user upgrade — green;
- explicit rollback — green;
- default Qt cutover — complete;
- post-cutover black-box regression — green;
- cleanup reachability — audited;
- rollback retention — hardened.

REL-10 itself is documentation/release truth only.

## Deliberate limitations

The audit confirms these remain intentional and do not block V2 2.0.0:

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

## Final gate

REL-10 and the optional exact-SHA docs handoff must have:

- all four CI jobs green;
- no unresolved substantive P1/P2;
- exact `main` verification after squash merge.

After that, the release/cutover batch is closed and development stops until a separate user-directed batch begins.
