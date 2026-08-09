# Nemexia Raid Manager V2 — UI/UX redesign batch

Date: 2026-08-09
Audit baseline: `c728380e889d86b3b4d38b64ae48e3ecab275ad9`
Audit: `docs/audits/2026-08-09-v2-uiux-redesign-audit.md`

## Goal

Bring every current PySide6 surface into one reusable Orbital Command 2.0 design system without changing browser capabilities, business/mutation contracts, persistence semantics or the default launcher.

## Hard boundaries for the whole batch

- Presentation/composition only in `v2/ui`, plus presentation/smoke tests and docs.
- Existing context/application calls may be rearranged visually but not replaced by new action routes.
- No browser launch, tab creation, `goto`, `refreshGalaxy`, planet/system switching or background navigation.
- Navigation decision from V2-67 remains `NO NAVIGATION BOUNDARY`.
- No changes to SendFleet/processSpy execution, persistent journals, idempotency keys, retry rules or ambiguity recovery.
- CAPTCHA remains detect → STOP.
- AutoFarm state machine/scheduler behavior remains unchanged; only its screen hierarchy changes.
- Asteroid/debris bounded workflows and manual Stop semantics remain unchanged.
- `run_app.bat -> app_entry.py` remains the default launcher.
- `app_qt.py` remains opt-in.
- Legacy SQLite remains read-only.
- All existing safety tests are preserved.

## V2-UI-01 — audit / batch contract

Research/docs only.

Deliver:

- current PySide6 vs Orbital Command audit;
- frozen component/tokens requirements;
- page-by-page redesign map;
- responsive/smoke acceptance criteria;
- explicit visual-only safety boundary.

No runtime code.

## V2-UI-02 — reusable design system + shell

Create the presentation foundation before page-specific redesign.

Expected scope:

- extend `v2/ui/theme.py` with frozen semantic tokens and complete QSS states;
- add `v2/ui/components.py` or equivalent Qt-only reusable presentation helpers;
- standardize typography, spacing, radii, buttons, badges, inputs, cards, toolbars, state banners, empty/error states and tables;
- redesign `MainWindow`, sidebar and topbar using the same routes/page order;
- keep topbar informational: no new live/browser probe or game action.

Required tests:

- component/source contract contains no browser/application mutation imports;
- launcher contract remains unchanged;
- shell navigation remains the same 11 pages;
- focus/disabled/warning/danger styles are present;
- minimum/default window dimensions remain 1180×720 / 1440×900.

## V2-UI-03 — Overview

Redesign the dashboard on top of the frozen component system.

Preserve:

- no live probe during construction;
- explicit `Обновить live` action;
- existing `refresh_live_source()`/snapshot flow;
- current persisted facts.

Target:

- state banner;
- consistent KPI cards;
- live capacity/readiness summary;
- saved-event freshness area;
- useful empty/unavailable presentation.

## V2-UI-04 — Plan + Active

### Plan

- separate queue-policy controls from mutation controls;
- warning visual semantics for the real send action;
- preparation stays visually safe/read-only;
- persistent action status/incident treatment;
- table remains filterable/sortable/read-only.

### Active

- compact live source/capacity/unresolved journal summary;
- live table remains primary content;
- explicit refresh remains the only live read trigger on this page.

No action/journal/reconciliation semantics change.

## V2-UI-05 — AutoFarm operational screen

Make AutoFarm the strongest operational full-page screen in V2.

Visual hierarchy:

1. typed farm state / armed state / safety status;
2. primary operational controls and Stop;
3. wave parameters;
4. exact session-only Spy fleet recovery input;
5. current metrics / next condition / cooldown;
6. last operation/result and concise safety contract.

Preserve exactly:

- starts disarmed;
- 30-second scheduler interval;
- explicit start confirmation;
- exact Spy fleet ID requirement;
- safety-stop states;
- one journaled controlled recon path;
- no automatic retry after ambiguous side effect;
- session-only armed state and Spy fleet ID.

## V2-UI-06 — Recon + Targets + History

Apply the shared data/command patterns.

Recon:

- exact-fleet command card;
- safe ingest visually separated from remote processSpy/refill actions;
- status banner;
- no new spy route.

Targets:

- search/table/empty-state consistency only;
- no CRUD added.

History:

- intentionally sparse search/table presentation;
- semantic status/error readability;
- no new actions.

## V2-UI-07 — Asteroids + Debris

Build one sibling visual pattern without merging their workflow semantics.

Shared visual structure:

- Source / Fleet / Safety field groups;
- current-system read action;
- preparation action;
- warning remote dispatch action;
- separated danger Stop;
- attach-only/no-navigation state banner;
- evidence/candidate table.

Asteroid keeps its existing bounded prepare/dispatch behavior.

Debris keeps its separate preparation token + explicit confirmation lifecycle and current-system evidence states.

Automatic 3×40 traversal remains forbidden.

## V2-UI-08 — Settings + Diagnostics

Settings:

- scrollable grouped cards based on current allow-listed V2 settings only;
- dedicated action-gate warning block;
- same persistence method and validation.

Diagnostics:

- no automatic browser probe;
- consistent definition-list cards;
- selectable technical paths/facts;
- cached live source status only.

## V2-UI-09 — final consistency / two-size Qt gate

Update `ci/qt_smoke.py` and presentation contract tests to cover:

- 1180×720;
- 1440×900;
- all 11 stack pages;
- every page selectable without layout failure;
- no page minimum geometry forcing a larger main window;
- AutoFarm disarmed/timer inactive at construction;
- Settings/dense pages scroll rather than force resize;
- existing explicit Active refresh test still behaves identically;
- legacy database bytes unchanged;
- V2 DB integrity and existing persistence checks unchanged.

Final source-contract gate must assert that `v2/ui` did not gain browser/navigation primitives.

## Per-stage discipline

Each implementation stage uses a fresh branch from exact current `main` after the prior squash push-CI is green.

For every stage:

1. verify exact main SHA;
2. reread affected UI files and source-contract tests;
3. make presentation-only change;
4. run full CI;
5. inspect review threads/findings;
6. fix substantive findings without weakening safety assertions;
7. squash merge;
8. record exact squash SHA;
9. verify exact post-merge push-CI before opening the next branch.

## CI

Existing gate remains mandatory:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: offscreen Qt smoke.

V2-UI-09 strengthens the Qt smoke to the two required geometries; it does not replace the existing functional/safety checks.