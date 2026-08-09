# AUTO-06 — Browser Readiness Manager

Date: 2026-08-09

Baseline: `8ce38e94d7b467fe991d4f005d604bda61d611ce` (AUTO-05 squash PR #132, post-main CI #310 green).

## Scope

AUTO-06 turns the AUTO-04/AUTO-05 navigation primitives into an application-level readiness contract. Normal recoverable page state is prepared by V2 instead of being returned as a technical manual-page instruction.

This PR changes automation/application behavior only. The visual readiness panel belongs to a separate UI-only PR.

## Readiness model

`BrowserReadinessSnapshot` exposes:

```text
Browser
Account
Planet
Fleets
Messages
Galaxy
```

Each component has a human label, state and detail. States are `ready`, `not_ready`, `blocked`, and `stopped`. CAPTCHA evidence maps to `stopped` and automation does not continue.

## Safe automatic preparation

`BrowserReadinessManager` imports no browser selectors. It delegates all context changes to `NavigationCoordinator` and therefore retains the persistent exactly-one journal.

It can:

- resolve an intended coordinate only through the proven own-planet set and switch by PlanetIdentity when required;
- prepare Fleets;
- prepare System messages;
- prepare Galaxy.

Every needed preparation gets a fresh immutable `readiness:<kind>:<uuid>` request ID. Already-ready state causes no remote effect.

## Production workflow integration

Production now uses `AutomationReadyApplicationContext`.

Normal recoverable workflows request their required surface automatically:

- live flight refresh → Fleets;
- recon read/ingest → System messages;
- raid prepare/dispatch → configured own `farm_home` when present, then Fleets;
- asteroid observation → Galaxy;
- debris observation → Galaxy.

AUTO-06 does not hide the current spy backend's two-surface limitation. AUTO-07 owns automatic exact-fleet discovery and the verified recon sequence.

Galaxy page preparation is automatic here; galaxy/system selection remains AUTO-09 because `refreshGalaxy/ajax_galaxy.php` has its own mutation contract.

## Mutation session reconnect policy

Production mutation-capable CDP paths now use a shared no-auto-reconnect guard:

- NavigationCoordinator backend;
- raid backend;
- spy backend;
- asteroid backend.

The initial CDP attach is allowed. If an established mutation session is later lost, the backend fails closed instead of silently attaching to a new session. Explicit recovery is deferred to AUTO-13.

Pure read-only debris access is not changed by this guard.

## Remaining manual work

Full parity is not reached. The user may still need to:

1. start/keep a CDP-capable browser and one authenticated Nemexia game tab available initially;
2. resolve zero/multiple initial game tabs until explicit session recovery exists;
3. choose an exact spy fleet ID until AUTO-07;
4. choose galaxy/system coordinates until AUTO-09;
5. start the 3×40 scan manually until AUTO-10;
6. restart asteroid cycles manually until AUTO-11;
7. wait for Rest Mode until AUTO-12;
8. recover a lost established mutation session manually until AUTO-13.

These remain AUTO-14 parity blockers.

## Safety invariants

- CAPTCHA remains a hard stop;
- request IDs remain immutable;
- one remote effect per journal request;
- ambiguous effects are not automatically repeated;
- account, planet and page context stay verified around navigation;
- legacy SQLite stays read-only;
- V2 journals stay persistent;
- Qt/application code contains no browser selectors;
- legacy bulk spy processing is not restored;
- debris repeat is not invented.
