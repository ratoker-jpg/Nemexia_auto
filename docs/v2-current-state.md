# Nemexia Raid Manager V2 — current state

Release: **V2 2.0.0 / PySide6 Qt default**  
Release date: 2026-08-09  
REL-10 exact squash: `adf1c8318a1a0ffbe79cec2ffd23200cbbc375b5` / PR #125  
REL-10 exact post-merge push-CI: **#287 green**

## Production entrypoints

Default production runtime:

```text
run_app.bat -> app_qt.py -> PySide6 V2
```

Explicit tested rollback:

```text
run_legacy.bat -> app_entry.py -> legacy Tkinter
```

Default Windows package:

```text
NemexiaRaidManager.spec -> app_qt.py -> NemexiaRaidManager.exe
```

Legacy fallback package:

```text
NemexiaRaidManagerLegacy.spec -> app_entry.py -> NemexiaRaidManagerLegacy.exe
```

The Tkinter stack is intentionally retained as a tested rollback surface. REL-08 proved no production legacy file was safely removable, and REL-09 therefore performed zero production deletions.

## Canonical release baselines

| Area | Exact squash SHA | Gate |
|---|---|---|
| Raid action migration V2-31→V2-40 | `a3db5b277ecea3ef5358a9cd9b0e3f93eebb8dd9` | typed raid mutation/journal baseline |
| Fresh recon/refill V2-41→V2-50 | `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` | PR #82 |
| Asteroid action migration V2-51→V2-58 | `b5d57bf620a1567b63f15a29ac8ff382692fd943` | PR #92 |
| Action migration final / debris V2-59→V2-66 | `1077125a59a96274017ad09c9814431bdaeb614e` | PR #101 / exact push-CI #206 green |
| V2 SQLite schema 9 | `70cbc13ccde6e0545083341f6c7a5ebbbe70628a` | PR #103 / exact push-CI #214 green |
| Navigation contract V2-67 | `6cbd7f88d41a8c065980de47a38e2a27063d31a2` | PR #104 / `NO NAVIGATION BOUNDARY` / CI #216 green |
| UI/UX final action baseline | `8d9c3c548ed74f6b2b55533489b9834126a65908` | PR #114 / exact push-CI #243 green |
| UI docs handoff | `074834d60b2647f18f32c43c4b6810ba91033b79` | PR #115 / exact push-CI #245 green |
| Qt default cutover REL-06 | `54ca45eeffea2da8f4fbebdcbcbe28d8b8dc30c5` | PR #121 / exact push-CI #276 green |
| Post-cutover gate REL-07 | `fd0992bb8eba2d236ffb867e4a034c2aa15b1153` | PR #122 / exact push-CI #278 green |
| Legacy reachability audit REL-08 | `925d28a8a56436135ea9d134e6a9a52bf2236294` | PR #123 / exact push-CI #281 green |
| Rollback retention REL-09 | `2a21fbc9d97de39fabb2bf658f700b3d57851980` | PR #124 / exact push-CI #285 green |
| Final release docs REL-10 | `adf1c8318a1a0ffbe79cec2ffd23200cbbc375b5` | PR #125 / exact push-CI #287 green |

## Release/cutover status

**REL-01→REL-10 are complete.** Production cutover is closed; this release batch must not open new feature work automatically.

- **REL-01** — Tkinter → PySide6 user-visible parity audit.
- **REL-02** — production V2 startup/shutdown lifecycle, backup boundaries and restart recovery.
- **REL-03** — Windows Qt install/package preparation.
- **REL-04** — real clean-install + existing-user upgrade matrix.
- **REL-05** — independent tested Tk fallback.
- **REL-06** — authorized default launcher/package cutover to Qt.
- **REL-07** — post-cutover black-box regression gate.
- **REL-08** — complete legacy reachability audit; result `D. PROVEN DEAD = ∅`.
- **REL-09** — intentional NO-OP/HARDENING; zero production deletions.
- **REL-10** — V2 2.0.0 release docs/version/install/upgrade/rollback/final handoff.

Detailed records:

- `docs/audits/2026-08-09-v2-release-cutover-parity-audit.md`
- `docs/audits/2026-08-09-v2-legacy-reachability-audit.md`
- `docs/audits/2026-08-09-v2-rel09-rollback-retention.md`
- `docs/audits/2026-08-09-v2-final-release-audit.md`
- `docs/plans/2026-08-09-v2-release-cutover-batch.md`
- `docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md`

## V2 storage and recovery

Current V2 SQLite schema version: **9**.

V2 runtime storage:

```text
%LOCALAPPDATA%\NemexiaRaidManagerV2\
```

V2-owned state includes typed settings, raid actions/queue, spy actions, recon targets/reports, asteroid actions/observations and debris observations.

Production lifecycle creates V2 backups at accepted startup/shutdown boundaries, closes the context/database deterministically and preserves unresolved journals across restart rather than silently retrying remote effects.

Legacy SQLite remains strictly read-only from V2:

- SQLite URI `mode=ro`;
- `PRAGMA query_only=ON`;
- no V2 mutation of legacy targets/history/queue/recon/settings.

The existing-user upgrade gate checks legacy DB byte-integrity where required, accepted import into V2 storage, V2 restart persistence and database unlock after shutdown.

## PySide6 UI release state

The Qt design system and all 11 production routes are complete:

1. Overview;
2. Plan;
3. Active;
4. AutoFarm;
5. Asteroids;
6. Debris;
7. Recon;
8. Targets;
9. History;
10. Settings;
11. Diagnostics.

The Qt validation gate constructs a real `QApplication` / `MainWindow`, selects all 11 routes and validates:

```text
1180×720
1440×900
```

The final UI action baseline remains `8d9c3c548ed74f6b2b55533489b9834126a65908`.

## Browser boundary — authoritative

Decision remains **`NO NAVIGATION BOUNDARY`**.

V2 remains attach-only and does not silently acquire browser/account/planet ownership through navigation.

Live operations therefore require the relevant Nemexia surface to be already open/rendered before the user triggers the V2 action:

- `fleets.php` — fleet/capacity facts and raid/spy/asteroid/debris-send preparation/verification;
- `options.php` with already-rendered **System** messages — spy-report verification/ingestion;
- `galaxy.php` on the intended current system — explicit current-system asteroid/debris observation.

V2 does not automatically switch between these pages to satisfy a missing prerequisite.

Current release deliberately does **not** implement:

- automatic 3×40 traversal;
- background browser navigation;
- Rest Mode navigation loops;
- automatic `refreshGalaxy`;
- V2 `change_planet.php`;
- arbitrary V2 `page.goto` navigation;
- automatic browser launch/tab creation;
- V2-68 typed navigation intent;
- V2-69 single-step navigation;
- V2-70 navigation recovery/parity.

These are future feature contracts, not release blockers.

## Mutation/safety contracts

- Raid/asteroid/debris mutations remain typed, prepared/rechecked, journaled and exactly-one-attempt per accepted request.
- Ambiguous remote acceptance is never automatically retried.
- Spy/recon uses an exact existing processable fleet ID and never `processSpy(0)`.
- No new espionage route is created when no exact processable spy fleet exists.
- AutoFarm starts disarmed; explicit Start is required; arm and exact Spy fleet ID are session-only.
- There is no unattended asteroid/debris scheduler.
- CAPTCHA remains **detect → STOP**; solve/click/bypass is not implemented.
- Automatic message deletion is not implemented.

## Legacy rollback retention

REL-08 traced fallback reachability through `run_legacy.bat`, `run_console.bat`, `app_entry.py`, all ordered monkey-patch/install calls, legacy core transitives, legacy PyInstaller/build paths, installer dependencies, self-test, release fallback smoke, tests and evidence fixtures.

Result:

```text
D. PROVEN DEAD = ∅
```

Therefore **UNKNOWN ≠ DEAD** and no production legacy file was authorized for removal. REL-09 retained the stack and added a machine-readable retention manifest plus regression tests.

## Rollback refs

Verified and unchanged:

```text
stable/tkinter-v1 -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
archive/pre-pyside6-4e01bfda -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
```

Original stable Tkinter SHA:

```text
4e01bfda752c6383e48c0f6eb8be64d68676da67
```

## Final validation gate

REL-10 exact squash `adf1c8318a1a0ffbe79cec2ffd23200cbbc375b5` passed exact push-CI **#287** with:

- Windows Python 3.10 — compileall + full pytest + legacy self-test;
- Windows Python 3.11 — compileall + full pytest + legacy self-test;
- PySide6 / Python 3.11 — real QApplication/MainWindow, all 11 routes, 1180×720 + 1440×900;
- Windows release black-box — real `install.bat`, side-by-side clean/existing-user upgrade, `run_app.bat --release-smoke` = Qt/V2, `run_legacy.bat --release-smoke` = Tk/legacy, V2 restart, legacy DB integrity where required and database unlocked after shutdown.

The final exact-SHA handoff must pass the same CI/review discipline. After its exact post-merge push-CI is green, stop; do not begin V2-68/V2-69/V2-70, Rest Mode, browser navigation or new gameplay work automatically.
