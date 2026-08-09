# Nemexia Raid Manager V2 — current state

Current safe V2 baseline before this docs handoff:

- `8d9c3c548ed74f6b2b55533489b9834126a65908`
- PR #114 / V2-UI-09 — completed PySide6 UI/UX redesign + two-size consistency gate
- exact post-merge push-CI #243 — green on Windows Python 3.10, Windows Python 3.11 and PySide6 offscreen smoke

Current completed **action-migration** baseline remains:

- `1077125a59a96274017ad09c9814431bdaeb614e`
- PR #101 / V2-66 — debris/recycling parity gate
- exact push-CI #206 — green

Storage maintenance baseline:

- `70cbc13ccde6e0545083341f6c7a5ebbbe70628a`
- PR #103 — V2 SQLite schema 9 / versioned `debris_observations`
- exact post-merge push-CI #214 — green

Browser-navigation audit baseline:

- `6cbd7f88d41a8c065980de47a38e2a27063d31a2`
- PR #104 / V2-67
- decision: **`NO NAVIGATION BOUNDARY`**
- exact post-merge push-CI #216 — green

The UI redesign was visual-only. It did not reopen V2-68→V2-70, add browser navigation, alter mutation contracts, change schema 9 or cut the default launcher over to Qt.

## Completed V2 action batches

### Raid action migration — V2-31→V2-40

PR #62–#71 established typed raid commands, attach-only preparation, `actions_enabled`, exactly-one SendFleet attempt, persistent raid journal/idempotency, V2-owned queue, manual Plan dispatch, conservative reconciliation and the typed AutoFarm state machine.

Final batch baseline: `a3db5b277ecea3ef5358a9cd9b0e3f93eebb8dd9`.

### Fresh reconnaissance / refill — V2-41→V2-50

PR #73–#82 established attach-only spy-report reading, exact `processSpy(fleet_id)`, persistent spy journal, V2-owned recon targets/reports, deterministic refill, 25-minute successful-empty-scan cooldown and fail-closed recovery.

Final batch squash: `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` / PR #82.

### Asteroid action migration — V2-51→V2-58

PR #84–#92 established attach-only current-system asteroid reading, typed/persistent recycler dispatch, immutable observations/candidates, real Qt Asteroids page, bounded multi-selection, read-only preparation, explicit confirmation/manual Stop and conservative restart recovery.

Final batch squash: `b5d57bf620a1567b63f15a29ac8ff382692fd943` / PR #92.

### Debris / recycling migration — V2-59→V2-66

PR #94–#101 established exact debris evidence parsing, attach-only current-system read, immutable V2-owned debris evidence, deterministic candidates, reuse of the asteroid mutation/journal boundary, bounded controlled dispatch, real Qt Debris page and recovery/parity coverage.

Final batch squash: `1077125a59a96274017ad09c9814431bdaeb614e` / PR #101.

Detailed parity records remain under `docs/audits/`.

## Maintenance gate — V2 SQLite schema 9

PR #103 / `70cbc13ccde6e0545083341f6c7a5ebbbe70628a` removed the old structural split where two different databases could both claim schema 8.

Current V2 SQLite schema version: **9**.

Migration 9:

- installs `debris_observations` through the normal `V2Database` migration chain;
- records migration 9 before `PRAGMA user_version` advances;
- safely handles schema 8 both with and without the former feature-local debris table;
- preserves existing debris rows without duplication;
- preserves settings, raid actions/queue, spy actions, recon targets/reports and asteroid actions/observations;
- preserves debris evidence through backup/restore.

`DebrisObservationRepository` is data-access only and no longer owns schema creation.

## UI/UX redesign — V2-UI-01→V2-UI-09

The full visual-only batch completed PR #106–#114.

Final action baseline:

```text
8d9c3c548ed74f6b2b55533489b9834126a65908
```

Exact push-CI #243 is green.

Detailed parity record: [`audits/2026-08-09-v2-uiux-redesign-parity-gate.md`](audits/2026-08-09-v2-uiux-redesign-parity-gate.md).

### Frozen design system

`v2/ui/theme.py` now owns semantic presentation tokens:

- cold dark surface hierarchy;
- primary/secondary/muted text;
- blue safe/read/preparation primary;
- amber remote-action/arm warning;
- red Stop/danger;
- green success/result;
- spacing `4 / 8 / 12 / 16 / 24 / 32`;
- radii `6 / 8 / 12`;
- stable control/sidebar/topbar/table sizes;
- Segoe UI hierarchy + Consolas technical facts;
- hover/focus/disabled/selected/input/table/scroll/dialog states.

`v2/ui/components.py` is a Qt-only reusable presentation layer with `StatusPill`, `MetricCard`, `StateBanner`, `SectionCard`, `EmptyState`, semantic command buttons, page/scroll scaffolds and toolbars.

The component layer does not own browser, persistence or action logic.

### Redesigned shell

MainWindow preserves the same 11 routes and grouped navigation:

- Overview;
- Plan;
- Active;
- AutoFarm;
- Asteroids;
- Debris;
- Recon;
- Targets;
- History;
- Settings;
- Diagnostics.

The shell now uses a consistent 220 px sidebar, ~80 px topbar, page title/description hierarchy and persistent informational V2 / attach-only / legacy-read-only status pills. The topbar does not probe the browser or trigger game actions.

### Redesigned page behavior

- **Overview** — read-only/storage state banner, KPI cards, explicit live readiness refresh and persisted event freshness. No live probe at construction.
- **Plan** — local queue policy visually separated from read-only preparation and warning-coded real SendFleet dispatch. Existing confirmation/idempotency/no-retry contract unchanged.
- **Active** — compact live source/capacity/unresolved-journal layer above the flight table. Refresh remains explicit.
- **AutoFarm** — primary operational command screen with typed state, wave controls, session-only exact Spy recovery, Start/Stop, safety contract and last result. State machine remains unchanged.
- **Recon** — safe report ingestion separated visually from warning-coded exact-fleet `processSpy`/controlled refill.
- **Targets / History** — shared read-only data pattern with search, semantic alignment, horizontal scrolling and visible empty states. No CRUD added.
- **Asteroids / Debris** — sibling Source / Recyclers / Safety command layout, current-system read, preparation, warning dispatch/confirmation and danger Stop. Their workflow semantics remain separate.
- **Settings** — scrollable Connection / Account context / Farm timing / Safety gate groups using only current allow-listed V2 settings.
- **Diagnostics** — scrollable no-probe factual view using cached live status only; local technical paths are selectable.

### Required desktop geometries

The final Qt smoke now covers both:

```text
1180×720
1440×900
```

All 11 pages are selected at both sizes. Fixture-backed populated Active state is explicitly reloaded at both sizes so the minimum-size result is not based on an empty table.

The final gate verifies actual page/window geometry and hard minimums; wide tables are allowed to expose horizontal scroll rather than forcing main-window expansion.

Three real layout problems were found and fixed during V2-UI-09:

1. Plan controls were wrapped into compact multi-row grids for the ~960 px content viewport at 1180×720.
2. AutoFarm became vertically scrollable at the 720 px minimum height while preserving the complete operational screen.
3. Wide data/evidence tables became shrinkable with horizontal overflow owned by the table scrollbar.

AutoFarm, Settings and Diagnostics use scroll areas where required. AutoFarm remains disarmed and its timer inactive during construction/geometry checks.

A global source-contract scans the complete `v2/ui` tree and rejects direct browser/navigation primitives including `BrowserWorker`, Playwright, `goto`, `new_page`, `refreshGalaxy`, `change_planet.php` and browser launch.

## Safety baseline

Rollback refs remain untouched:

- `stable/tkinter-v1`
- `archive/pre-pyside6-4e01bfda`
- original stable Tkinter SHA `4e01bfda752c6383e48c0f6eb8be64d68676da67`

Default launcher remains:

```text
run_app.bat -> app_entry.py
```

PySide6 remains a separate opt-in entrypoint:

```text
app_qt.py
```

No Tkinter → Qt cutover has occurred.

## Storage boundary

Legacy SQLite remains strictly read-only:

- URI `mode=ro`;
- `PRAGMA query_only=ON`;
- no V2 mutation of legacy targets/history/queue/recon/settings.

V2-owned runtime storage remains under `%LOCALAPPDATA%/NemexiaRaidManagerV2/`.

V2-owned versioned state includes allow-listed typed settings, `raid_actions`, `raid_queue`, `spy_actions`, `recon_targets`, immutable `recon_reports`, `asteroid_actions`, immutable `asteroid_observations` and immutable `debris_observations`.

A `no_debris` result from one current system never deletes evidence learned from other systems.

## Browser boundary after V2-67

V2 remains strictly attach-only. It uses an existing Chromium/Yandex CDP session and does not launch the browser, create tabs or navigate the account automatically.

Current live prerequisites remain:

- already-open `fleets.php` for fleet/capacity/raid/spy/asteroid/debris-send facts;
- already-rendered System messages on `options.php` for spy-report verification;
- already-open `galaxy.php` for explicit current-system asteroid/debris observation.

V2 does **not** automatically switch pages, planets, galaxy systems or traverse 3×40 systems.

CAPTCHA remains strict detect → STOP.

Detailed navigation audit: [`audits/2026-08-09-v2-browser-navigation-contract-audit.md`](audits/2026-08-09-v2-browser-navigation-contract-audit.md).

The decision remains **`NO NAVIGATION BOUNDARY`**. The effective legacy galaxy path can change selected planet through `change_planet.php`; current bound-tab/V2 ownership does not prove stable account + selected-planet identity around navigation. V2-68, V2-69 and V2-70 remain blocked/not started.

## Mutation boundaries unchanged by UI redesign

### Raid

Requires `actions_enabled=true`; typed validation, read-only preparation, persistent request identity, exactly one SendFleet attempt, exact new-flight verification and no automatic retry after ambiguity remain unchanged.

### Spy / fresh-report

V2 never uses `processSpy(0)`. Mutation remains exactly one already-existing espionage row via `processSpy(fleet_id)` with persistent request identity, exact report verification and fail-closed ambiguity/CAPTCHA handling.

### AutoFarm

Continuous mode starts disarmed and requires explicit manual Start. Scheduler interval remains 30 seconds. Arm and exact Spy fleet ID are session-only. Pending/ambiguous effects, CAPTCHA, stale/no fresh evidence, live failure or wave failure disarm the cycle.

### Asteroid / debris

There remains exactly one authoritative recycler SendFleet boundary and one persistent `asteroid_actions` unresolved trajectory journal for both generic asteroid and debris execution.

Controlled dispatch still performs typed validation, read-only preparation, movement/capacity/recycler/CAPTCHA re-checks, exactly one SendFleet attempt, exact new-flight verification and no automatic retry after ambiguity.

Debris has no second SendFleet implementation and no `debris_actions` journal.

Manual Stop never cancels an already-started remote attempt; it blocks the next one after the current attempt settles. There is no asteroid/debris auto-repeat scheduler.

## Explicitly deferred / blocked

Still not enabled in V2:

- automatic message deletion;
- automatic CAPTCHA interaction;
- unattended browser launch/navigation;
- any V2 `page.goto`, `refreshGalaxy`, `ajax_galaxy.php` navigation POST or `change_planet.php` action;
- automatic galaxy/system traversal, including legacy 3×40 debris scanning;
- Rest Mode page-opening/refresh loops;
- background navigation;
- V2-68 typed navigation intent under the current evidence set;
- V2-69 single-step navigation;
- V2-70 navigation recovery/parity;
- creation of a new espionage route when no exact processable spy fleet row exists;
- asteroid/debris auto-repeat schedulers;
- default launcher cutover to Qt;
- deletion of legacy Tkinter/patch modules.

## Verification gate

Every implementation/docs gate remains:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

The Qt smoke additionally enforces the two required window geometries and global V2 UI navigation source-contract.

After every squash merge, push-CI must be verified on the exact new `main` SHA before any new branch starts.