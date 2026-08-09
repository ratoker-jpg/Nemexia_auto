# Nemexia Raid Manager V2 — REL-09 rollback retention hardening

Date: 2026-08-09
Starting baseline: `925d28a8a56436135ea9d134e6a9a52bf2236294`
Source audit: `docs/audits/2026-08-09-v2-legacy-reachability-audit.md`

## Decision

REL-09 is intentionally a **NO-OP with respect to production cleanup**.

REL-08 classified `D. PROVEN DEAD = ∅`. Therefore this stage deletes or archives **zero** legacy production files. The tested Tkinter stack remains an explicit rollback product surface, not accidental source residue.

## What this stage hardens

- `docs/audits/v2-legacy-retained-rollback-files.txt` is the machine-readable retention manifest for the current fallback.
- A regression test requires every manifest path to exist.
- The regression test also pins the split:
  - DEFAULT: `run_app.bat -> app_qt.py`
  - ROLLBACK: `run_legacy.bat -> app_entry.py`
- The independent legacy PyInstaller spec/build path remains required.
- The Windows release job must continue to execute the legacy fallback smoke after a real install.
- The legacy self-test remains mandatory on Windows Python 3.10 and 3.11.

## Explicit non-actions

This stage does **not**:

- delete `app_entry.py`;
- delete or archive any legacy patch/installer module;
- remove `browser.py`, `storage.py`, `models.py`, `reports.py`, `asteroids.py` or other legacy core;
- remove `run_legacy.bat`, `run_console.bat`, the legacy spec, or legacy build path;
- remove shared dependencies merely because Qt is the default;
- classify UNKNOWN evidence/artifacts as dead;
- change Qt/V2 browser, storage, mutation, scheduler or UI behavior.

Any future removal requires a new reachability audit after an explicit rollback-retirement decision. That work is outside the current release batch.

## Release safety remains unchanged

- V2 SQLite schema remains 9.
- V2 legacy SQLite access remains read-only.
- `NO NAVIGATION BOUNDARY` remains authoritative.
- no automatic 3×40 traversal;
- no V2 background browser navigation / Rest Mode navigation loops;
- no automatic `refreshGalaxy`, `change_planet.php`, or arbitrary `page.goto` navigation;
- CAPTCHA remains detect → STOP;
- no automatic message deletion;
- no automatic retry after ambiguous remote side effect;
- no new espionage route without an exact processable spy fleet;
- no unattended asteroid/debris scheduler.

## REL-10 handoff

After REL-09 exact post-merge CI is green, REL-10 may update release/version/install/upgrade/rollback documentation only. No new gameplay or navigation feature is authorized by this retention decision.
