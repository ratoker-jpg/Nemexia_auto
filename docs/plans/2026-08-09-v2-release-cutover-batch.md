# Nemexia Raid Manager V2 — release / cutover batch

Date: 2026-08-09
Starting baseline: `074834d60b2647f18f32c43c4b6810ba91033b79`
Parity audit: `docs/audits/2026-08-09-v2-release-cutover-parity-audit.md`

## Goal

Make PySide6 the production default only after startup/storage, Windows install/package, side-by-side upgrade and rollback gates prove that cutover is recoverable and does not weaken the V2 safety model.

## Hard boundaries

- No new browser navigation capability during release work.
- V2-67 `NO NAVIGATION BOUNDARY` remains authoritative.
- No automatic browser launch/tab creation/system or planet traversal.
- No automatic 3×40 scan or Rest Mode navigation loop.
- CAPTCHA remains detect → STOP.
- No weakening of raid/spy/asteroid/debris journals, idempotency, exactly-one mutation attempt or ambiguity handling.
- Legacy SQLite remains read-only to V2.
- Keep rollback refs untouched.
- Keep a tested legacy fallback through the first Qt-default release.
- Do not remove Tkinter runtime/patch code before REL-08 reachability audit.

## REL-01 — user-visible parity audit

Docs/research only.

Deliver:

- exhaustive Tkinter → PySide6 user-visible feature matrix;
- classify parity, safer replacement, intentional safety exclusion and fallback-only/deferred conveniences;
- identify cutover blockers;
- freeze release/cutover sequencing.

Decision at audit baseline: **CUTOVER BLOCKED** until REL-02→REL-05 are green.

## REL-02 — production startup/shutdown + backup/restart recovery

Expected implementation:

- production lifecycle helper around V2 startup;
- create a consistent V2 backup at the accepted startup boundary before normal user operation proceeds;
- clear failure reporting without deleting/corrupting live DB;
- deterministic context/database close;
- restart recovery tests across all V2-owned state/journals;
- clean-first-start test without legacy/V2 DB;
- backup integrity/restore test from the production lifecycle path.

Must not change launcher default.

## REL-03 — Windows Qt launcher/installer/package preparation

Prepare, do not cut over.

Expected implementation:

- `install.bat` installs the shared side-by-side dependency set including PySide6;
- source launcher support for an explicit Qt launch path while legacy remains default;
- independent legacy fallback launcher;
- Qt-capable PyInstaller spec/build path;
- Windows source-contract tests for commands/dependencies/entrypoints;
- compile/smoke both entrypoints.

`run_app.bat` must still default to `app_entry.py` after REL-03.

## REL-04 — clean-install + existing-user side-by-side gate

Windows CI gate with isolated temporary `%LOCALAPPDATA%` roots.

Scenario A — clean install:

- no legacy DB and no V2 DB;
- legacy and Qt startup smokes can both run;
- storage roots remain isolated;
- Qt never launches/navigates browser.

Scenario B — existing-user upgrade:

- seed representative legacy DB/settings/queue/recon facts;
- run Qt bootstrap/import;
- assert legacy DB bytes unchanged;
- assert accepted migration facts appear in V2-owned DB;
- restart Qt and preserve V2 state;
- assert legacy startup remains usable against original DB.

No default-launcher switch yet.

## REL-05 — explicit rollback/fallback gate

Prove:

- stable `run_legacy.bat` fallback command;
- fallback uses legacy entrypoint/storage;
- Qt failure leaves fallback intact;
- rollback refs remain documented and untouched;
- release smoke can invoke the fallback independently.

No default-launcher switch yet.

## REL-06 — default Qt launcher cutover

Authorized only after exact post-merge push-CI for REL-02, REL-03, REL-04 and REL-05 is green.

Scope must stay small:

- switch `run_app.bat` default command to `app_qt.py`;
- make Qt the default PyInstaller entrypoint if packaging gate is green;
- preserve explicit legacy fallback;
- update launcher messages/tests only as required.

No feature/browser/mutation/cleanup work.

## REL-07 — post-cutover smoke/regression gate

Prove on exact Qt-default main:

- default launcher contract points only to Qt;
- legacy fallback still points only to Tk;
- clean/eexisting-user lifecycle matrix still passes;
- two-size Qt UI gate remains green;
- all Python 3.10/3.11 tests + legacy self-test remain green;
- V2 SQLite integrity/backups/restart recovery green;
- no browser navigation primitives were introduced.

## REL-08 — legacy cleanup audit

Docs/research only.

Inventory every legacy Tk/patch/runtime module by reachability from:

- `run_legacy.bat` / legacy entrypoint;
- retained legacy package/spec, if any;
- legacy self-test and parity tests;
- recovery/support tooling;
- docs/evidence fixtures.

Classify:

- required fallback runtime;
- required tests/support;
- archive-only evidence;
- proven dead/unreachable.

No deletion in REL-08.

## REL-09 — remove/archive proven-dead legacy code

Delete or archive only files classified proven dead by REL-08.

Rules:

- retained fallback must remain executable;
- no speculative cleanup;
- no deletion just because a file is old or patch-shaped;
- source-contract tests must prove removed modules have no remaining imports/references;
- if nothing is safely removable, REL-09 is a documented no-op rather than forced deletion.

## REL-10 — final release docs/version/handoff

Finalize:

- release version/changelog;
- default Qt startup and explicit legacy fallback instructions;
- clean install and existing-user upgrade notes;
- V2 data/backup locations;
- rollback procedure;
- intentional legacy parity exclusions;
- exact final squash SHA and post-merge CI run;
- current safety/browser/mutation boundaries.

## Per-stage discipline

Every stage:

1. verify exact current `main`;
2. start a fresh branch only after prior exact post-merge push-CI is green;
3. reread affected runtime/tests/docs;
4. make the smallest stage-scoped change;
5. run full CI;
6. inspect review threads/findings;
7. fix substantive findings without weakening release/safety assertions;
8. squash merge;
9. record exact squash SHA;
10. verify exact push-CI on new `main` before the next branch.

## Required CI baseline

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: offscreen Qt smoke at 1180×720 and 1440×900.

Release stages may add Windows lifecycle/package/cutover checks; they must not replace existing gates.
