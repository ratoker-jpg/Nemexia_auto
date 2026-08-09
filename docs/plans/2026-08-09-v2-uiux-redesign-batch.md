# Nemexia Raid Manager V2 — UI/UX redesign batch

Date: 2026-08-09
Audit baseline: `c728380e889d86b3b4d38b64ae48e3ecab275ad9`
Audit: `docs/audits/2026-08-09-v2-uiux-redesign-audit.md`
Final parity gate: `docs/audits/2026-08-09-v2-uiux-redesign-parity-gate.md`

## Status — COMPLETE

V2-UI-01→V2-UI-09 is fully merged.

- V2-UI-01 / PR #106 / `a7ce531224be7bfc0d36a72e88dd3165c5925033` — audit + batch contract; exact push-CI #220 green.
- V2-UI-02 / PR #107 / `3045a4902fd243b8b6bac113f43ebc4192967593` — reusable Qt design system + MainWindow/sidebar/topbar; exact push-CI #222 green.
- V2-UI-03 / PR #108 / `b73594bc0077a0e2021cdd31d6f52d37440cae98` — Overview; exact push-CI #224 green.
- V2-UI-04 / PR #109 / `9aa14ed65ff17a8f31f27bce71288eb740341771` — Plan + Active + table presentation; exact push-CI #226 green.
- V2-UI-05 / PR #110 / `c58bf1ac91fff31a381ced9fd660f4a1e0b89214` — full-page AutoFarm command screen; exact push-CI #228 green.
- V2-UI-06 / PR #111 / `ba10219607feb95a88570e843eb9cef831856908` — Recon + Targets + History; exact push-CI #230 green.
- V2-UI-07 / PR #112 / `3344c0c6dfd03a47cd835d26a09ca5e6a4b2fe46` — Asteroids + Debris; exact push-CI #232 green.
- V2-UI-08 / PR #113 / `0802439e8c67edb2985da4e5dcacc2ddabd95f9c` — Settings + Diagnostics; exact push-CI #234 green.
- V2-UI-09 / PR #114 / `8d9c3c548ed74f6b2b55533489b9834126a65908` — final 1180×720 + 1440×900 consistency/safety gate; exact push-CI #243 green.

## Goal achieved

Every current PySide6 surface now uses one reusable Orbital Command 2.0 presentation system without changing browser capabilities, business/mutation contracts, persistence semantics or the default launcher.

## Hard boundaries preserved

- Existing context/application calls were rearranged visually but not replaced by new action routes.
- No browser launch, tab creation, `goto`, `refreshGalaxy`, planet/system switching or background navigation.
- V2-67 decision remains **`NO NAVIGATION BOUNDARY`**.
- No changes to SendFleet/processSpy execution, persistent journals, idempotency keys, retry rules or ambiguity recovery.
- CAPTCHA remains detect → STOP.
- AutoFarm state machine/scheduler behavior remains unchanged.
- Asteroid/debris bounded workflows and manual Stop semantics remain unchanged.
- `run_app.bat -> app_entry.py` remains the default launcher.
- `app_qt.py` remains opt-in.
- Legacy SQLite remains read-only.
- V2 SQLite remains schema 9.

## Frozen visual system

`v2/ui/theme.py` owns semantic colors, typography, spacing, radii, control sizes and QSS states. `v2/ui/components.py` provides the reusable Qt-only primitives used by the redesigned pages.

Accepted spacing remains `4 / 8 / 12 / 16 / 24 / 32`; card/control radii remain `12 / 6–8`; Segoe UI is the primary Windows UI family and Consolas is restricted to technical facts.

Action semantics are explicit:

- blue — safe/read/preparation primary action;
- amber — real remote action or operational arm;
- red — Stop/danger;
- green — success/result state rather than the default send color.

Status is never color-only.

## Completed page scope

### Shell

MainWindow, grouped sidebar and topbar share the same tokens/components while preserving all 11 routes and informational-only topbar behavior.

### Overview

Persisted KPI/status hierarchy, explicit attach-only live readiness and event freshness. No live probe at construction.

### Plan + Active

Plan separates deterministic queue policy from read-only preparation and warning-coded real dispatch. Active keeps live refresh explicit and makes capacity/journal a compact control layer above the flights table.

### AutoFarm

AutoFarm is the primary operational screen: typed state, wave controls, session-only exact Spy recovery, continuous Start/Stop, safety contract and last result. It starts disarmed and keeps the existing 30-second scheduler/state machine.

### Recon + Targets + History

Recon separates safe ingestion from remote exact-fleet actions. Targets/History stay read-only and gain consistent data/empty states. No CRUD or new spy route was added.

### Asteroids + Debris

Both pages share one visual command language while keeping separate workflow semantics. Both remain current-system attach-only and expose manual Stop. Automatic 3×40 traversal remains absent.

### Settings + Diagnostics

Settings is scrollable and groups only the current allow-listed fields. Diagnostics is scrollable, selectable and no-probe; cached live status only.

## V2-UI-09 geometry findings

The final gate found and forced fixes for three real presentation problems:

1. Plan controls were too wide for the ~960 px content viewport inside a 1180 px window; controls were changed to compact multi-row grids.
2. AutoFarm's complete operational content was too tall for the 720 px minimum; the page now scrolls vertically rather than shrinking or forcing resize.
3. Wide evidence/data tables produced large advisory width; table/card size policy now permits shrinking and the existing horizontal scrollbar owns overflow.

The gate checks actual hard minimum/page/window geometry rather than treating Qt's advisory `minimumSizeHint()` as a mandatory page width.

Populated fixture-backed Active state is explicitly reloaded at both required geometries so the gate is not based on an empty table.

## Final acceptance gate

`ci/qt_smoke.py` now covers:

- exact `1180×720` and `1440×900` windows;
- all 11 current pages;
- populated Active rows/capacity at both sizes;
- actual page/window geometry that does not force main-window expansion;
- AutoFarm/Settings/Diagnostics scroll behavior;
- AutoFarm disarmed/timer-inactive construction state;
- Settings persistence;
- Diagnostics cached-status behavior;
- legacy SQLite byte integrity;
- V2 SQLite integrity and recon persistence.

A global source-contract also rejects direct browser/navigation primitives anywhere under `v2/ui` and keeps the default launcher pinned to `app_entry.py`.

## Per-stage discipline record

Every implementation stage was created from fresh exact `main` after the previous squash push-CI was green. Every stage passed Windows Python 3.10/3.11 full pytest + legacy self-test and PySide6 offscreen smoke before the next stage began.

The final visual action baseline is:

```text
8d9c3c548ed74f6b2b55533489b9834126a65908
```

PR #114 / exact push-CI #243 green.

This batch does **not** authorize a default Qt launcher cutover or reopening browser-navigation implementation.