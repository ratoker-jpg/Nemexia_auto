# Nemexia Raid Manager V2 — full automation parity + UI consolidation

Date: 2026-08-09

Production baseline before this post-release plan:

- release 2.0.0 final main before the reference handoff: `596678b2eccf50587c0d3425a0c8254ec79609a1`;
- Qt is production default: `run_app.bat -> app_qt.py`;
- tested rollback remains: `run_legacy.bat -> app_entry.py`;
- V2 SQLite schema: 9;
- legacy SQLite remains read-only from V2.

Reference evidence for this plan:

- [`../reference/2026-08-09-user-browser-screen-reference.md`](../reference/2026-08-09-user-browser-screen-reference.md)
- [`../fixtures/browser_reference/automation_contract_snippets.html`](../fixtures/browser_reference/automation_contract_snippets.html)

The previous `NO NAVIGATION BOUNDARY` remains a safety fact about the **current implementation**, not the desired final product UX.

## Product goal

V2 must become a practical replacement for the original automation, not a UI that requires the operator to manually maintain the correct browser page.

Target acceptance criterion:

> The user starts and controls workflows from Qt. Browser/account/planet/page/system preparation is performed by a centralized, verified V2 automation layer. Required manual browser servicing from the legacy workflow should be eliminated where the effective legacy runtime already automated it and where V2 can prove before/after identity safely.

Safety is not relaxed:

- CAPTCHA = STOP; never solve/click/bypass;
- one remote mutation attempt per immutable request;
- no automatic retry after ambiguous remote effect;
- legacy SQLite remains V2 read-only;
- account/planet/page context mutations must be verified;
- rollback remains available.

# Track A — automation parity

## AUTO-01 — effective legacy automation parity audit

Research only.

Inventory effective `app_entry.py`, `BrowserWorker`, installed patch modules, tests and build/runtime call sites. Produce a matrix:

```text
LEGACY FEATURE
CURRENT V2
MISSING
REQUIRED V2 CONTRACT
RISK
IMPLEMENTATION ORDER
```

Cover at least:

- browser start/discovery/connect;
- tab/page selection and creation;
- owned-planet discovery;
- selected-planet switching / `change_planet.php`;
- `fleets.php`;
- `options.php` + System messages;
- `galaxy.php`;
- galaxy/system switching and `refreshGalaxy` / `ajax_galaxy.php`;
- recon/report acquisition;
- creation of a spy route if effective legacy can do it;
- 3×40 asteroid/debris traversal;
- asteroid/debris repeat/autorenew;
- Rest Mode / attack watch;
- background loops;
- return-to-expected-planet/page behavior;
- CAPTCHA;
- message cleanup;
- recovery after browser/manual operator interference.

Do not implement navigation in AUTO-01.

## AUTO-02 — typed BrowserSession / AccountContext / PlanetIdentity

Read-only identity proof.

First-class `PlanetIdentity` must include at least:

- internal planet ID;
- coordinate;
- display name;
- active/selected proof;
- owning account/server context evidence where available.

Use the real supplied DOM contract:

```text
#planetSwitch
#planetsListHolder
change_planet.php?id=<planet_id>
```

Qt settings/workflows must eventually select `PlanetIdentity`, not free-form coordinate strings.

## AUTO-03 — central NavigationCoordinator + persistent context journal

Single owner for browser context changes.

It owns:

- CDP/browser session identity;
- exact bound tab/page identity;
- Nemexia server identity;
- proven account identity;
- selected planet identity;
- starting URL/page kind;
- intended planet/page/system destination;
- navigation/context mutex;
- before/after evidence;
- persistent immutable request identity for server-side context mutations;
- VERIFIED / AMBIGUOUS / FAILED_SAFE recovery.

No feature page may call `goto`, `change_planet.php`, `refreshGalaxy` or equivalent directly.

## AUTO-04 — verified planet switching

Implement one explicit planet-context step through the coordinator.

Required:

```text
prepare current account/tab/planet
→ journal immutable request
→ exactly one selected-planet mutation
→ verify same account + expected planet
→ VERIFIED / AMBIGUOUS / FAILED_SAFE
```

No retry after ambiguous outcome.

## AUTO-05 — verified page preparation

Centralized preparation of required existing/new game page state for:

- `fleets.php`;
- `options.php` System messages;
- `galaxy.php`.

The user should no longer need to manually open these pages as normal UX.

Must verify page kind + account + selected planet after preparation.

Checkpoint after AUTO-05: state exactly what the operator still has to do manually.

## AUTO-06 — Browser Readiness Manager + human UX

Expose:

```text
Browser   connected / unavailable
Account   identified / ambiguous
Planet    selected
Fleets    ready
Messages  ready
Galaxy    ready
```

Replace technical user-facing errors such as `live_unavailable: open options.php...` with human recovery actions.

## AUTO-07 — automatic recon workflow

From Qt:

```text
prepare browser/account/planet/messages/fleets
→ discover processable spy fleet
→ process exact fleet
→ observe/verify fresh report
→ ingest
→ deterministic refill
```

Do not require the operator to type exact fleet ID if the live DOM can prove it.

The supplied reference shows both:

```text
#spy1Link-<fleet_id> / processSpy(<fleet_id>)
#spy1Time-<fleet_id>
```

Use those states explicitly.

## AUTO-08 — espionage route parity

Audit before mutation.

If effective legacy creates a new espionage route when no processable spy fleet exists, migrate it as its own typed, journaled exactly-one action. If legacy does not prove this, do not invent the contract.

## AUTO-09 — verified galaxy/system step

Use one centralized coordinator step with before/after:

- account;
- selected planet;
- galaxy/system destination;
- CAPTCHA/login redirect detection.

This is prerequisite to full traversal.

## AUTO-10 — controlled automatic 3×40 discovery

Restore legacy-equivalent asteroid/debris traversal only on top of AUTO-09.

Requirements:

- deterministic progress;
- explicit Start/Stop;
- CAPTCHA STOP;
- incomplete scan never claims completion;
- last completed scan semantics;
- restart/recovery;
- no silent skip interpreted as `no_debris`;
- V2-owned evidence.

## AUTO-11 — asteroid/debris repeat parity

Only if effective legacy proves auto-repeat/autorenew behavior.

Implement through typed scheduler/state, never UI strings.

## AUTO-12 — Rest Mode parity

Only after verified navigation ownership exists.

No old monkey-patch navigation reuse.

## AUTO-13 — full automation recovery

Cover:

- browser closed;
- tab lost;
- login redirect;
- operator manually changes planet/page;
- crash mid-navigation;
- crash mid-game mutation;
- CAPTCHA;
- stale account context;
- restart.

## AUTO-14 — automation parity gate

Re-run the matrix. Do not claim full parity while the user still has mandatory manual browser work that effective legacy automated.

# Track B — UI consolidation and visual polish

UI work must be separate PRs from browser/business changes.

## Information architecture target

The 11 migration-era routes are implementation-friendly but too fragmented for the final product.

Target main navigation:

```text
Обзор
Фарм
Разведка
Астероиды
История
Настройки
```

Mapping:

- `Фарм` = AutoFarm + Plan + Active as one operational surface with internal tabs/sections;
- `Разведка` = Recon + Targets;
- `Астероиды` = Asteroids + Debris;
- `Настройки` = Settings + Diagnostics;
- `Обзор` and `История` remain top-level.

Do not delete application/domain services merely because pages are consolidated.

## Planet/account header

Once AUTO-02 is available, working surfaces should expose a consistent account/planet control, e.g.:

```text
ACCOUNT      PLANET            BROWSER
Ares         HOME [coord] ▼    ● ready
```

Planet selection is a first-class typed control.

## Visual defect pass

Real Windows use found unintended near-black strips behind labels/rows inside cards.

Audit all six consolidated surfaces / underlying 11 page widgets for:

- nested `QWidget/QFrame/QLabel` backgrounds;
- accidental black row rectangles;
- QScrollArea viewport backgrounds;
- table viewport/header backgrounds;
- card padding/spacing;
- border/radius consistency;
- clipping;
- hover/focus/disabled states;
- empty/error/loading states;
- modal styling;
- horizontal/vertical scroll ownership.

Keep gameplay logic unchanged in UI-only PRs.

## Visual QA artifacts

At 1180×720 and 1440×900:

- instantiate populated representative states, not only empty fixtures;
- capture screenshots for all principal surfaces as CI artifacts where practical;
- use them for manual review;
- do not rely on fragile pixel-perfect assertions as the only gate.

# Parallel delivery discipline

Automation PRs and UI PRs may progress in parallel, but a single PR must not mix unrelated browser/business and visual-only changes.

For every PR:

1. verify exact current `main`;
2. fresh branch;
3. focused change;
4. full tests;
5. review substantive P1/P2;
6. squash merge;
7. exact post-merge push-CI green before dependent work.

After AUTO-05, produce a checkpoint before starting AUTO-06+.

# Explicit non-goals

Full automation does **not** mean:

- CAPTCHA solving/clicking/bypass;
- blind retry after ambiguous remote effect;
- bypassing journals/idempotency;
- direct browser calls from Qt page widgets;
- writing legacy SQLite;
- deleting rollback merely because Qt is default.

# Final product acceptance

The project is ready to call `FULL AUTOMATION PARITY` only when:

- the main workflows start from Qt;
- owned planets are discovered and selectable in V2;
- required pages are prepared by the application;
- recon no longer requires manually opening System messages or typing fleet IDs where live proof exists;
- asteroid/debris scan can perform the legacy-equivalent traversal under verified context;
- browser/account/planet interference fails closed and recovers safely;
- the main navigation is consolidated to the product-oriented six-section structure;
- known visual artifacts such as black background strips are fixed;
- all safety invariants and rollback remain green.
