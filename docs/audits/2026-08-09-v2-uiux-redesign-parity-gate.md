# Nemexia Raid Manager V2 — UI/UX redesign parity gate

Date: 2026-08-09
Original visual baseline: `c728380e889d86b3b4d38b64ae48e3ecab275ad9`
Final visual action baseline: `8d9c3c548ed74f6b2b55533489b9834126a65908`
Final action PR: #114 / V2-UI-09
Exact post-merge push-CI: #243 — green on Windows Python 3.10, Windows Python 3.11 and PySide6 offscreen smoke.

## Decision

**V2 UI/UX redesign batch V2-UI-01→V2-UI-09 is complete.**

The current opt-in PySide6 application now implements one reusable Orbital Command 2.0 presentation system across all 11 current pages while preserving the pre-batch browser, action, storage and launcher contracts.

## Source concept

The redesign was grounded in:

- `REPORT_UI_VISUAL_CONCEPT.md`;
- `docs/audits/2026-08-06-ui-ux-audit.md`;
- `docs/audits/2026-08-07-current-ui-visual-animation-audit.md`;
- `docs/audits/2026-08-09-v2-uiux-redesign-audit.md`.

The accepted character remains dark, strict and technological rather than decorative: strong information hierarchy, low visual noise, semantic action risk and dense desktop data surfaces that still fit the minimum supported window.

## Completed stages

- V2-UI-01 / PR #106 / `a7ce531224be7bfc0d36a72e88dd3165c5925033` — audit and visual-only batch contract; exact push-CI #220 green.
- V2-UI-02 / PR #107 / `3045a4902fd243b8b6bac113f43ebc4192967593` — frozen Qt design system + MainWindow/sidebar/topbar; exact push-CI #222 green.
- V2-UI-03 / PR #108 / `b73594bc0077a0e2021cdd31d6f52d37440cae98` — Overview redesign; exact push-CI #224 green.
- V2-UI-04 / PR #109 / `9aa14ed65ff17a8f31f27bce71288eb740341771` — Plan + Active redesign and table density/alignment; exact push-CI #226 green.
- V2-UI-05 / PR #110 / `c58bf1ac91fff31a381ced9fd660f4a1e0b89214` — AutoFarm operational command screen; exact push-CI #228 green.
- V2-UI-06 / PR #111 / `ba10219607feb95a88570e843eb9cef831856908` — Recon + Targets + History redesign; exact push-CI #230 green.
- V2-UI-07 / PR #112 / `3344c0c6dfd03a47cd835d26a09ca5e6a4b2fe46` — Asteroids + Debris sibling command surfaces; exact push-CI #232 green.
- V2-UI-08 / PR #113 / `0802439e8c67edb2985da4e5dcacc2ddabd95f9c` — Settings + Diagnostics redesign; exact push-CI #234 green.
- V2-UI-09 / PR #114 / `8d9c3c548ed74f6b2b55533489b9834126a65908` — two-size full-page consistency/safety gate; exact push-CI #243 green.

## Frozen design system

`v2/ui/theme.py` now owns semantic presentation tokens instead of page-local styling drift:

- cold dark surfaces and border hierarchy;
- primary/secondary/muted text roles;
- blue informational/safe-primary accent;
- amber warning/action risk;
- red danger/Stop;
- green success/status;
- spacing rhythm `4 / 8 / 12 / 16 / 24 / 32`;
- radii `6 / 8 / 12`;
- stable sidebar/topbar/control/table dimensions;
- Segoe UI hierarchy and Consolas for technical facts;
- focus/disabled/hover/selected states;
- input, table, horizontal scrollbar and QMessageBox styling.

`v2/ui/components.py` provides reusable Qt-only presentation primitives:

- `StatusPill`;
- `MetricCard`;
- `StateBanner`;
- `SectionCard`;
- `EmptyState`;
- semantic command buttons;
- page/scroll scaffolds and toolbars.

The component layer does not import browser adapters, persistence repositories or action services.

## Shell parity

`MainWindow` preserves the same 11 routes and the accepted grouped navigation:

- Overview;
- Operations: Plan, Active, AutoFarm, Asteroids, Debris;
- Data: Recon, Targets, History;
- System: Settings, Diagnostics.

The shell now has one consistent 220 px sidebar, ~80 px topbar, page title/description hierarchy and persistent informational safety pills including V2 / attach-only / legacy read-only status. No browser probe or game action was added to the shell.

## Page results

### Overview

Persisted-data state banner, four KPI cards, explicit attach-only live readiness area and persisted event freshness. Construction still performs no live browser probe; `Обновить live` remains explicit.

### Plan + Active

Plan visually separates deterministic local queue policy, read-only preparation and warning-coded real SendFleet dispatch. Existing confirmation/idempotency/no-retry behavior is unchanged.

Active makes live source/capacity/unresolved journal a compact control layer and keeps the flight table as the main content. Live refresh remains explicit.

### AutoFarm

AutoFarm is now the strongest operational screen: typed farm/armed state, wave controls, session-only exact Spy recovery, continuous-cycle Start/Stop, safety contract and last result are visually distinct.

The state machine is unchanged: 30-second scheduler, process starts disarmed, exact Spy fleet ID remains session-only, ambiguity/CAPTCHA/live failure/unresolved journal disarm the cycle and no ambiguous side effect is retried automatically.

At 1180×720 the full command screen scrolls vertically instead of forcing the main window larger.

### Recon + Targets + History

Recon separates safe report ingestion from warning-coded exact-fleet `processSpy`/controlled-refill actions while preserving all confirmation and exact-report contracts.

Targets and History use the shared read-only data pattern with search, semantic alignment, horizontal scrolling and visible empty states. No CRUD was added.

### Asteroids + Debris

Both pages share Source / Recyclers / Safety → current-system read → preparation → warning dispatch/confirmation → danger Stop visual structure and a permanent attach-only/current-system state.

Their workflow semantics remain separate:

- Asteroids keeps bounded prepare → dispatch + manual Stop;
- Debris keeps preparation token invalidation → separate explicit confirmation ID → bounded shared asteroid journal dispatch + manual Stop.

No galaxy/system navigation or 3×40 traversal was introduced.

### Settings + Diagnostics

Settings is scrollable and groups only the existing allow-listed fields: Connection, Account context, Farm timing and Safety gate. It still writes through one `set_v2_settings(values)` operation.

Diagnostics is a scrollable no-probe factual screen. It shows legacy read-only source, cached live status, V2 paths/storage and runtime facts; it never initiates a browser refresh.

## Two-size gate findings

The strengthened V2-UI-09 smoke did not merely instantiate the window. It exercised all 11 pages at both required geometries and discovered three real layout issues before merge:

1. **Plan width** — long single-row controls pushed the page beyond the 1180 px window after sidebar allocation. Fixed by compact multi-row/grid composition.
2. **AutoFarm height** — the full operational command screen exceeded the 720 px minimum. Fixed with a vertical page scroll while preserving the complete content hierarchy.
3. **Wide evidence tables** — table content produced a large advisory width. Fixed with shrinkable table/card size policy plus horizontal scrolling; the final gate checks actual window/page geometry rather than treating Qt's advisory `minimumSizeHint()` as a hard width.

The final smoke also reloads fixture-backed populated Active state at **both** geometries so the minimum-size result is not based only on an empty table.

## Final geometry/smoke contract

`ci/qt_smoke.py` now proves:

- exact main window sizes `1180×720` and `1440×900` remain stable while selecting all 11 pages;
- no page hard minimum or actual geometry forces the window larger;
- fixture-backed Active rows/capacity render at both sizes;
- AutoFarm, Settings and Diagnostics use scroll areas where required;
- AutoFarm starts disarmed and its timer remains inactive during construction/geometry checks;
- legacy SQLite bytes remain unchanged;
- V2 SQLite integrity remains `ok`;
- V2 settings persistence and recon evidence checks remain valid.

A global source-contract test also scans the complete `v2/ui` tree and rejects direct browser/navigation primitives such as `BrowserWorker`, Playwright, `goto`, `new_page`, `refreshGalaxy`, `change_planet.php` and browser launch.

## Safety parity

The visual batch did **not** change:

- V2 SQLite schema 9;
- legacy SQLite read-only mode;
- raid SendFleet contract or raid journal;
- exact-fleet `processSpy` contract or spy journal;
- asteroid/debris shared mutation journal;
- bounded confirmation/manual Stop semantics;
- CAPTCHA detect → STOP;
- no automatic retry after possible remote side effect;
- AutoFarm state-machine semantics;
- attach-only browser boundary;
- V2-67 `NO NAVIGATION BOUNDARY`;
- automatic 3×40 traversal remains absent;
- Rest Mode/background navigation remains absent;
- default launcher remains `run_app.bat -> app_entry.py`;
- `app_qt.py` remains opt-in.

## Final conclusion

The PySide6 application has reached visual-system parity with the accepted Orbital Command direction for the current feature set. Future Qt pages should use the frozen semantic tokens/components rather than introducing page-local design systems.

This gate does **not** authorize a default Qt launcher cutover or any browser-navigation work.