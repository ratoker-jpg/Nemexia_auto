# Nemexia Raid Manager V2 — current state

Release: **V2 2.0.0 / PySide6 Qt default**  
Release date: 2026-08-09  
REL-10 starting baseline: `2a21fbc9d97de39fabb2bf658f700b3d57851980` / REL-09.

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

The Tkinter stack is retained intentionally as a tested rollback surface. REL-08 found no production legacy file that was positively proven dead, and REL-09 therefore performed zero production deletions.

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
| Final release docs REL-10 | recorded by the post-merge release handoff | must have exact green push-CI |

## Release/cutover status

REL-01→REL-09 are complete. REL-10 finalizes release truth/documentation only; it does not change game/browser/storage behavior.

Release progression:

- **REL-01** — full Tkinter → PySide6 user-visible parity audit; classified intentional safety exclusions and release blockers.
- **REL-02** — production V2 startup/shutdown lifecycle, mandatory backup boundaries and restart recovery.
- **REL-03** — Windows Qt install/package preparation while legacy remained default.
- **REL-04** — real clean-install + existing-user upgrade matrix with storage isolation and legacy DB integrity.
- **REL-05** — independent `run_legacy.bat` rollback and black-box fallback proof.
- **REL-06** — authorized default launcher/package cutover to Qt after all prerequisites were green.
- **REL-07** — post-cutover black-box regression gate on Qt-default main.
- **REL-08** — complete legacy reachability audit; result `D. PROVEN DEAD = ∅`.
- **REL-09** — intentional NO-OP/HARDENING; zero production deletions, retained rollback manifest + regression gates.
- **REL-10** — release 2.0.0 documentation/version/handoff.

Detailed records:

- `docs/audits/2026-08-09-v2-release-cutover-parity-audit.md`
- `docs/audits/2026-08-09-v2-legacy-reachability-audit.md`
- `docs/audits/2026-08-09-v2-rel09-rollback-retention.md`
- `docs/plans/2026-08-09-v2-release-cutover-batch.md`
- `docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md`

## V2 storage and recovery

Current V2 SQLite schema version: **9**.

V2 runtime storage lives under:

```text
%LOCALAPPDATA%\NemexiaRaidManagerV2\
```

V2-owned versioned state includes:

- allow-listed typed settings;
- `raid_actions`;
- `raid_queue`;
- `spy_actions`;
- `recon_targets`;
- immutable `recon_reports`;
- `asteroid_actions`;
- immutable `asteroid_observations`;
- immutable `debris_observations`.

Production lifecycle creates V2 backups at accepted startup/shutdown boundaries, closes the V2 context/database deterministically and preserves unresolved journals across restart rather than silently clearing them.

Legacy SQLite remains strictly read-only from V2:

- SQLite URI `mode=ro`;
- `PRAGMA query_only=ON`;
- no V2 mutation of legacy targets/history/queue/recon/settings.

The release upgrade gate uses isolated `%LOCALAPPDATA%` roots and checks legacy DB byte integrity where the import contract requires it, V2 restart persistence and database unlock after shutdown.

## PySide6 UI release state

The frozen Qt design system and all 11 production routes are complete:

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

The Qt smoke constructs a real `QApplication` / `MainWindow`, selects every route and validates both required geometries:

```text
1180×720
1440×900
```

The final UI action baseline remains `8d9c3c548ed74f6b2b55533489b9834126a65908`; release/cutover work did not reopen visual redesign or change gameplay contracts.

## Browser boundary — authoritative

Decision remains **`NO NAVIGATION BOUNDARY`**.

V2 remains attach-only. It may inspect/use an already-open compatible Nemexia page through CDP but does not acquire account/planet ownership by navigating it automatically.

Current live prerequisites remain operation-specific:

- already-open `fleets.php` for fleet/capacity/raid/spy/asteroid/debris-send facts;
- already-rendered System messages on `options.php` for spy-report verification;
- already-open `galaxy.php` for explicit current-system asteroid/debris observation.

The following are **not implemented in the Qt release and must not appear implicitly through release work**:

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

### Raid

Requires the existing enable/safety gates, typed validation, read-only preparation, persistent request identity, exactly one remote SendFleet attempt, exact new-flight verification and no automatic retry after ambiguity.

### Spy / recon

V2 uses only exact existing processable espionage rows via `processSpy(fleet_id)`. It never uses `processSpy(0)` and does not create a new espionage route when no exact processable row exists.

### AutoFarm

Continuous mode starts disarmed and requires explicit manual Start. Scheduler interval remains 30 seconds. Arm and exact Spy fleet ID are session-only. Pending/ambiguous effects, CAPTCHA, stale/no fresh evidence, live failure or wave failure disarm the cycle.

### Asteroid / debris

Both workflows reuse the authoritative recycler mutation boundary and persistent unresolved trajectory journal. Preparation/re-check precedes exactly one remote attempt; ambiguity is not automatically retried. Manual Stop blocks future attempts but cannot undo an already-started remote side effect.

There is no unattended asteroid/debris scheduler and no automatic 3×40 current-release navigation.

### CAPTCHA / messages

CAPTCHA remains **detect → STOP**. Solve/click/bypass is not implemented. Automatic message deletion is not implemented.

## Legacy rollback retention

REL-08 proved that the current fallback reaches the legacy stack through multiple live roots:

- `run_legacy.bat -> app_entry.py`;
- `run_console.bat -> app_entry.py`;
- `NemexiaRaidManagerLegacy.spec -> app_entry.py`;
- `build_legacy_exe.bat`;
- `install.bat`;
- legacy self-test;
- release fallback smoke;
- direct ordered monkey-patch/install calls from `app_entry.py`.

Therefore **UNKNOWN ≠ DEAD**, and no legacy production file was authorized for removal.

REL-09 retained the stack and added a machine-readable retention manifest plus tests. Any future removal requires a new explicit rollback-retirement/reachability audit.

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

## Required final validation gate

Every release/handoff main must be green on:

- **Windows Python 3.10** — compileall + full pytest + legacy self-test;
- **Windows Python 3.11** — compileall + full pytest + legacy self-test;
- **PySide6 / Python 3.11** — real QApplication/MainWindow, all 11 routes, 1180×720 + 1440×900;
- **Windows release black-box** — real `install.bat`, side-by-side clean/existing-user upgrade, `run_app.bat --release-smoke` = Qt/V2, `run_legacy.bat --release-smoke` = Tk/legacy, V2 restart, legacy DB integrity where required, database unlocked after shutdown.

No release stage may weaken these gates. After every squash merge, exact push-CI must be verified on the new `main` SHA.
