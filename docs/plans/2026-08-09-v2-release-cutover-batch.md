# Nemexia Raid Manager V2 — release / cutover batch

Date: 2026-08-09  
Starting baseline: `074834d60b2647f18f32c43c4b6810ba91033b79`  
Status: **REL-01→REL-10 COMPLETE after final post-merge handoff**  
Release: **V2 2.0.0 / PySide6 Qt default**

Parity audit: `docs/audits/2026-08-09-v2-release-cutover-parity-audit.md`  
Legacy cleanup audit: `docs/audits/2026-08-09-v2-legacy-reachability-audit.md`  
Rollback retention: `docs/audits/2026-08-09-v2-rel09-rollback-retention.md`  
Release handoff: `docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md`

## Final result

The release goal is achieved: PySide6 became production default **only after** backup/restart, Windows install/package, clean/existing-user side-by-side and explicit rollback gates were green.

```text
DEFAULT:  run_app.bat    -> app_qt.py    -> PySide6 V2
ROLLBACK: run_legacy.bat -> app_entry.py -> legacy Tkinter
```

V2 SQLite schema remains **9** and legacy SQLite remains read-only from V2.

## Completed stages

| Stage | Result | Exact squash / gate |
|---|---|---|
| REL-01 | Tkinter→Qt user-visible parity audit; cutover blockers frozen | PR #116 / `3dd579ae589a56f402fbb2707498b4fe341c8821` |
| REL-02 | production startup/shutdown backup + restart recovery | PR #117 / `eea834cbff8511c813ff440c74249b516ee2130a` |
| REL-03 | Windows shared Qt+legacy install/package preparation | PR #118 / `a53fcc9882ad79810c6d5e5e5bf8b10b1b46b0cf` |
| REL-04 | real clean-install + existing-user upgrade matrix | PR #119 / `5a824f31a2bf903e028aa391405f4447a58d63b5` |
| REL-05 | independent tested Tk fallback | PR #120 / `11d470d8d1e8d5024e49cfaebd7bf6056167b12e` |
| REL-06 | authorized Qt default launcher/package cutover | PR #121 / `54ca45eeffea2da8f4fbebdcbcbe28d8b8dc30c5`; exact push-CI #276 green |
| REL-07 | post-cutover default Qt black-box regression | PR #122 / `fd0992bb8eba2d236ffb867e4a034c2aa15b1153`; exact push-CI #278 green |
| REL-08 | legacy reachability audit; `D. PROVEN DEAD = ∅` | PR #123 / `925d28a8a56436135ea9d134e6a9a52bf2236294`; exact push-CI #281 green |
| REL-09 | intentional NO-OP/HARDENING; zero production deletions | PR #124 / `2a21fbc9d97de39fabb2bf658f700b3d57851980`; exact push-CI #285 green |
| REL-10 | final release/version/install/upgrade/rollback/current-state docs | exact squash and push-CI recorded by post-merge handoff |

## Hard boundaries retained through release

Release work did **not** add new gameplay/navigation capability.

Authoritative constraints:

- V2-67 **`NO NAVIGATION BOUNDARY`**;
- no automatic browser launch/tab creation;
- no automatic 3×40 traversal;
- no background browser navigation;
- no Rest Mode navigation loops;
- no automatic `refreshGalaxy`;
- no V2 `change_planet.php`;
- no arbitrary V2 `page.goto`;
- CAPTCHA detect → STOP; no solve/click/bypass;
- no automatic message deletion;
- no automatic retry after ambiguous remote side effect;
- no new espionage route when no exact processable spy fleet exists;
- no unattended asteroid/debris scheduler;
- legacy SQLite read-only to V2;
- exactly-one mutation/idempotency journals remain authoritative.

These are deliberately deferred feature contracts and do not block release 2.0.0.

## REL-08 / REL-09 cleanup decision

REL-08 audited reachability from:

- `run_legacy.bat` and `run_console.bat`;
- `app_entry.py` and all ordered monkey-patch/install calls;
- legacy `app/browser/storage/models/reports/asteroids` transitives;
- `NemexiaRaidManagerLegacy.spec` / `build_legacy_exe.bat`;
- shared installer/dependencies;
- legacy self-test and release fallback smoke;
- tests/evidence fixtures.

Result:

```text
D. PROVEN DEAD = ∅
```

Therefore REL-09 correctly deleted **nothing**. It retained the tested fallback and added a machine-readable retention manifest/regression contract. `UNKNOWN != DEAD` remains the cleanup rule.

## Required release validation

Every final release/handoff main must pass all four jobs:

1. **Windows Python 3.10**
   - compileall;
   - full pytest;
   - legacy self-test.
2. **Windows Python 3.11**
   - compileall;
   - full pytest;
   - legacy self-test.
3. **PySide6 / Python 3.11**
   - real `QApplication` / `MainWindow`;
   - all 11 routes;
   - 1180×720;
   - 1440×900.
4. **Windows release black-box**
   - real `install.bat`;
   - clean/existing-user side-by-side smoke;
   - `run_app.bat --release-smoke` = Qt/V2;
   - `run_legacy.bat --release-smoke` = Tk/legacy;
   - legacy DB unchanged by V2 import where required;
   - V2 restart;
   - database unlocked after shutdown.

No red CI or unresolved substantive P1/P2 is acceptable.

## Rollback refs

Must remain unchanged:

```text
stable/tkinter-v1 -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
archive/pre-pyside6-4e01bfda -> 4e01bfda752c6383e48c0f6eb8be64d68676da67
```

## Stop condition

After REL-10 exact post-merge CI and, if required, the tiny exact-SHA docs handoff are green, this batch is closed. Do **not** automatically start V2-68/V2-69/V2-70, Rest Mode, browser navigation or any new gameplay feature.
