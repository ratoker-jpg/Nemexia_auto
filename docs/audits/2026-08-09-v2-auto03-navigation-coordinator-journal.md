# AUTO-03 — central NavigationCoordinator + persistent context journal

Date: 2026-08-09

Baseline: `7b736924a43851c24c4ae1efa451c23d4d1cdaa5` (AUTO-02 squash PR #129, push CI #296 green).

## Scope

AUTO-03 creates the single ownership boundary required before any navigation mutation:

- one `NavigationCoordinator` in the production V2 context;
- one navigation-owned runtime Nemexia `Page` binding;
- one process mutex serializing observation/future context mutations;
- persistent exactly-one navigation request journal in the V2-owned SQLite database;
- no `goto`, planet switch, page preparation, `refreshGalaxy`, spy action or fleet send in this stage.

## Runtime page ownership

`V2NavigationCdpBackend` binds exactly one already-open `fleets.php` page. Initial ambiguity (multiple matching tabs) fails closed. After binding, a closed/replaced/context-changed page fails closed instead of silently rebinding to another tab.

The in-process `page_token` identifies that exact Playwright `Page` object for the lifetime of the process. It is deliberately not treated as restart-stable identity; AUTO-13 will rebuild runtime ownership and reconcile persisted journal facts from observable account/planet/page evidence.

## Persistent journal

`navigation_actions` stores:

- immutable `request_id`;
- action kind;
- `pending / verified / ambiguous / failed_safe` state;
- canonical before context;
- immutable intent;
- optional after context;
- detail + timestamps.

Navigation journal schema is independently versioned by `navigation_schema_migrations` inside the same V2-owned database. Core `PRAGMA user_version` remains schema 9 in AUTO-03; legacy SQLite is untouched and remains read-only.

The journal already reserves action kinds for the later staged operations:

```text
bind_session
switch_planet
prepare_fleets
prepare_messages
prepare_galaxy
galaxy_system
```

Duplicate request IDs are rejected. Pending/ambiguous records remain persistent across process restart. Later stages may reconcile them only from read evidence; they may never repeat a remote effect merely because the previous result is uncertain.

## Production integration

`app_qt.py` now constructs exactly one NavigationCoordinator and passes it into the production application context. Existing raid/spy/asteroid backends keep their existing action semantics; they do not receive direct navigation permission in AUTO-03.

All new browser context mutations from AUTO-04 onward must be implemented only on the navigation backend and exposed only through `NavigationCoordinator`. Qt/features must not import Playwright/CDP selectors.

## Boundary after AUTO-03

Manual browser work is unchanged at runtime. In particular, the user must still provide the already-open `fleets.php` page required to establish initial ownership.

AUTO-04 is now authorized to add exactly one verified `change_planet.php` mutation primitive through this coordinator and journal. No other navigation mutation is opened by AUTO-03.
