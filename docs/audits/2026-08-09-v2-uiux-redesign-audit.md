# Nemexia Raid Manager V2 — UI/UX redesign audit

Date: 2026-08-09
Baseline: `c728380e889d86b3b4d38b64ae48e3ecab275ad9`
Scope: PySide6 presentation only.

## Decision

The V2 PySide6 application already uses the correct product direction — a dark Orbital Command desktop control panel — but it has not yet frozen that direction into a reusable design system. The redesign should therefore **consolidate and compose**, not recolor or invent new product behavior.

The batch is approved as a visual-only migration with these hard boundaries:

- no new browser capability;
- no `goto`, `new_page`, `refreshGalaxy`, planet/system switching, browser launch or background navigation;
- no mutation-contract changes;
- no change to raid/spy/asteroid/debris journals, confirmation, idempotency, retry or CAPTCHA semantics;
- no default-launcher cutover: `run_app.bat -> app_entry.py` remains unchanged;
- `app_qt.py` remains opt-in;
- all existing safety/source-contract tests remain authoritative.

## Source of truth

The audit compares current V2 against the accepted original visual direction recorded in:

- `REPORT_UI_VISUAL_CONCEPT.md`;
- `docs/audits/2026-08-06-ui-ux-audit.md`;
- `docs/audits/2026-08-07-current-ui-visual-animation-audit.md`.

The intended character remains **Orbital Command 2.0**: dark, strict, technological, dense but not crowded, with low visual noise and strong hierarchy from page → section → value → action.

## What current V2 already gets right

1. `MainWindow` already uses grouped persistent navigation: Overview / Operations / Data / System.
2. The shell already has the required target sizes: minimum `1180×720`, initial `1440×900`.
3. `theme.py` already starts from the accepted cold dark palette and uses a left accent rail for checked navigation.
4. Every real V2 page is connected through typed application context boundaries rather than direct browser/SQL logic.
5. Actions remain explicit: Plan, AutoFarm, Recon, Asteroids and Debris use confirmation/gating established by earlier safety batches.
6. Read-only data pages share one table model/view base.
7. AutoFarm starts disarmed and remains a session-only operational mode.
8. Asteroids and Debris already expose manual Stop and attach-only current-system wording.

These are invariants to preserve, not redesign targets.

## Core design-system gap

`v2/ui/theme.py` is currently one color map plus a small global QSS. Pages still own most presentation decisions locally:

- repeated `24 px` page margins;
- repeated card margins such as `18/16`;
- ad-hoc `QFrame#InfoCard` composition;
- local button object names without a complete semantic style mapping;
- local input dimensions;
- local status labels;
- local metric/card implementations;
- no shared toolbar, field, state-banner, empty-state or status-pill primitives;
- no reusable responsive page scaffold;
- no visual contract for dialogs;
- no frozen semantic table-column alignment model.

If page redesign begins before this is fixed, V2 will reproduce the same drift the original Tk audit identified.

## Frozen visual tokens

The redesign should retain the current V2 palette direction while normalizing it to semantic tokens.

### Color roles

```text
surface-0       #080D14   application background
surface-sidebar #0B121C
surface-1       #101925   cards/table body
surface-2       #152232   raised controls/header
surface-3       #1B2B3E   selected/hover emphasis
border-subtle   #213247
border-strong   #304765
text-primary    #F2F6FC
text-secondary  #A7B5C8
text-muted      #76889F   metadata/helper text
accent          #5B8CFF
accent-hover    #7AA4FF
success         #3BD18A
warning         #FFB454
error           #FF6270
```

Status must never be color-only.

### Spacing

Only the accepted rhythm should be used for new layouts:

```text
xs  4
sm  8
md 12
lg 16
xl 24
2xl 32
```

### Radius

```text
sm  6   compact controls/badges
md  8   inputs/buttons/nav
lg 12   cards/panels
```

### Typography

Segoe UI remains the Windows UI family; Consolas remains limited to technical/monospace facts.

```text
Display      24–28 / 700
PageTitle    24–26 / 600
SectionTitle 15–16 / 600
BodyStrong   13 / 600
Body         13 / 400
Caption      11 / 500–600
Metric       24–28 / 700
Mono         12–13 / 400
```

The purpose of a style, not a per-widget font tuple, determines typography.

### Control sizes

```text
button regular  36–38 px
button compact  30–32 px
input            36–38 px
compact toolbar  32 px
stable topbar    ~80 px
sidebar          ~220 px
```

## Semantic component contract

The redesign needs reusable presentation-only components/helpers for:

- page scaffold / scrollable page content;
- section/card;
- metric card;
- status pill/badge with text + semantic tone;
- state banner: info / success / warning / error;
- empty state and unavailable state;
- field group and helper text;
- command/action toolbar;
- primary / secondary / warning / danger / ghost buttons;
- compact button variants;
- consistent line edit / spin box / combo box / checkbox;
- data table/search shell;
- dialog spacing/tone through QSS without changing dialog decisions or callbacks.

The component module must import Qt/theme only. It must not import browser adapters, persistence repositories or mutation services.

## Button semantics

This batch must correct presentation semantics without changing handlers:

- **Primary blue** — main safe/read/preparation action;
- **Secondary** — helper/refresh/preview;
- **Warning amber** — action that can create a real remote side effect such as SendFleet/processSpy/starting an armed operational cycle;
- **Danger red** — stop/destructive action;
- **Success green** — result/status, not the default color for sending.

Disabled and keyboard-focus states must be explicit in QSS.

## Table contract

Current `FilterableReadOnlyTable` is structurally useful but visually under-specified.

Required redesign behavior:

- preserve `NoEditTriggers`, row selection, filtering and sorting;
- explicit horizontal scrollbar availability for wide tables;
- stable row/header density;
- text columns left aligned;
- numeric/resource/count columns right aligned;
- coordinates, short states and timestamps centered unless a page requires otherwise;
- Fleet/report IDs visually secondary where possible;
- no bright whole-row success/error fills;
- selected row remains high-contrast;
- empty model gets a visible non-error empty state rather than a blank expanse.

No sorting/filter semantics change is required.

## Shell audit

### Current

- 216 px sidebar;
- grouped text navigation;
- brand block;
- 76 px topbar;
- page title/description;
- one database/read-only status badge;
- pages also own their own 24 px margins.

### Redesign

- keep the same routes and groups;
- stronger brand/read-only identity but no decorative game UI;
- active nav: subtle surface + accent rail, not a heavy fill;
- stable ~80 px topbar;
- page title/description on left;
- compact persistent safety/status pills on right (e.g. V2, attach-only/read-only storage state), using already-known application state only;
- no new browser buttons or probes in topbar;
- remove double/inconsistent page padding by using a shared page scaffold.

## Page-by-page gap matrix

### Overview

Current V2 has four persisted-data KPI cards, a dense 8-value live grid and a saved-events card. It is factual but looks like three generic cards.

Redesign target:

- clear operational summary header/state banner;
- consistent KPI cards;
- live capacity/flight readiness presented as a legible operational strip/grid;
- last spy/raid facts visually secondary;
- explicit read-only refresh remains the only live action;
- no automatic probe on construction.

### Plan

Current page stacks search + queue builder + action row + wide table, with long horizontal control rows.

Redesign target:

- queue builder as a compact configuration card;
- mutation/preparation actions separated from pure queue policy;
- real `Отправить выбранную` styled warning/amber;
- action status as a persistent state banner/incident line rather than free text in the toolbar;
- table gets semantic alignment/horizontal scrolling;
- all existing prepare/send/refill methods and confirmations remain unchanged.

### Active

Current page is already clean but status, capacity and journal are three text lines in one card.

Redesign target:

- small status/metric strip for live source, capacity/free slots and unresolved journal;
- refresh remains explicit and read-only;
- flights table is the visual focus;
- Fleet ID and secondary scope facts receive lower visual weight.

### AutoFarm

This is the most important operational screen and should look like a command center, not a settings form.

Redesign target:

- full-page state hero with typed `FarmState`, armed/disarmed state and safety-stop reason;
- prominent Stop control whenever armed;
- clear next-state/next-check/cooldown presentation using existing state only;
- wave parameters in a compact control card;
- exact Spy fleet ID recovery field clearly separated as session-only evidence;
- one-wave and continuous-cycle actions visually distinct;
- long safety prose moved into concise persistent safety callouts without deleting the contract wording needed by source tests;
- recent operation/result line visible near current state.

No scheduler interval, state transition, recon recovery or mutation behavior changes are allowed.

### Recon

Current controls are one horizontal toolbar above the table.

Redesign target:

- exact Spy fleet ID in a compact command card;
- read/ingest action separated from remote `processSpy`/controlled-refill actions by visual risk;
- status becomes semantic banner;
- table remains dominant and read-only.

### Targets

Current page is generic search + table, which is acceptable for V2-owned read data.

Redesign target:

- data-page header/empty state consistency;
- semantic table alignment and horizontal scrolling;
- no new CRUD behavior added in this batch.

### History

Keep intentionally sparse:

- search + table;
- status/error visually legible;
- no decorative KPI layer;
- no new actions.

### Asteroids

Current page has one long row: source, recyclers, safety, read, prepare, send, stop.

Redesign target:

- sibling command layout shared with Debris;
- input groups: Source / Fleet / Safety;
- action group: current-system read → preparation → confirmed dispatch;
- Send action warning/amber; Stop danger and visually separated;
- attach-only/no-navigation state permanently visible;
- candidate table remains the evidence surface.

No automatic system switching/traversal is introduced.

### Debris

Same visual language as Asteroids, while preserving its stricter two-step preparation + confirmation token lifecycle.

The UI must continue to make these distinct:

- current-system evidence read;
- read-only preparation;
- explicit confirm dispatch;
- manual Stop;
- partial/no-debris/CAPTCHA/unavailable states.

Automatic 3×40 traversal remains absent.

### Settings

Current page is one card with one form.

Redesign target:

- scrollable page;
- groups based on the settings that **actually exist now**, not legacy wish-list fields:
  - Connection: CDP port;
  - Account context: farm home / command planet;
  - Farm timing: return buffer;
  - Safety: `actions_enabled`;
- `actions_enabled` gets a dedicated warning card because it changes the action gate;
- save remains a V2-local persistence action only.

### Diagnostics

Current page has three useful factual cards.

Redesign target:

- preserve no-probe rule;
- summarize legacy read-only source, cached live status, V2-owned storage and runtime in consistent definition-list cards;
- paths remain selectable and visually technical/monospace;
- explicit privacy/safety helper for local diagnostic paths if shown, without adding capture/navigation behavior.

## Responsive gate

The user-required visual gate is exactly:

- `1180×720` — minimum supported window;
- `1440×900` — default working window.

`ci/qt_smoke.py` must exercise both geometries offscreen and every page in the stack. The gate should verify:

- window can be laid out at both sizes;
- all 11 pages instantiate;
- each page can be selected and processed without side effects beyond the already-existing explicit Active refresh test;
- AutoFarm remains disarmed and timer inactive at construction;
- no page imposes a minimum size larger than the available content viewport;
- Settings and other dense pages use scrolling rather than forcing the main window larger;
- legacy SQLite bytes remain unchanged;
- existing V2 persistence checks still pass.

A smoke test is a structural geometry gate, not a pixel-perfect screenshot test.

## Safety source-contract for the visual batch

Add/retain tests that fail if the redesign introduces browser capability into `v2/ui`:

```text
BrowserWorker
playwright
new_page
goto(
refreshGalaxy
change_planet.php
launch_yandex
```

Existing typed context method names may remain because pages already invoke approved application services. The visual batch must not add a new mutation route or bypass existing confirmation/gate methods.

`run_app.bat` must remain unchanged and must continue to launch `app_entry.py` only.

## Implementation order

The safest visual migration order is:

1. freeze tokens/components and shell;
2. Overview;
3. Plan + Active;
4. AutoFarm;
5. Recon + Targets + History;
6. Asteroids + Debris;
7. Settings + Diagnostics;
8. two-size consistency/smoke gate and final handoff.

Each implementation PR starts from fresh `main` after the previous exact squash push-CI is green.

## Final audit conclusion

**Proceed with the UI/UX redesign.**

The current safety architecture does not need a functional rewrite to support it. The redesign can be performed entirely inside the PySide6 presentation layer plus visual/smoke tests, while preserving the V2 mutation, browser and launcher boundaries exactly as they stand.