# AUTO-04 — verified own-planet switching

Date: 2026-08-09

Baseline: `c7131cdc8d76b5fe9e1d7cdedaa91f36016b6131` (AUTO-03 squash PR #130, push CI #298 green).

## Scope

AUTO-04 opens exactly one remote navigation primitive in V2: switching the navigation-owned page to one already-proven own `PlanetIdentity`.

No generic page preparation, galaxy/system refresh, spy mutation or fleet send is added here.

## Exactly-one contract

`NavigationCoordinator.switch_planet(request_id, planet_id)`:

1. observes the exact bound runtime page and AccountContext;
2. resolves `planet_id` only from the proven owned-planet set;
3. persists immutable before/intent journal state;
4. if already selected, records `verified` with zero remote attempts;
5. otherwise invokes the navigation backend exactly once;
6. accepts success only if page token, server, account fingerprint, selected internal planet ID and selected coordinate all match;
7. if the backend throws after invocation, performs read-only reconciliation only;
8. unresolved/mismatching effects are persisted `ambiguous` and are never automatically retried.

Duplicate `request_id` values are rejected by the persistent journal before another remote attempt can be issued.

## Infrastructure mutation

`V2NavigationCdpBackend` finds the matching own anchor by all of:

```text
#planetsListHolder a
same game host
/change_planet.php
searchParams.id == PlanetIdentity.planet_id
anchor text contains PlanetIdentity.coord
```

It then performs one and only one:

```text
page.goto(proven_change_planet_href)
```

The same runtime `Page` object remains bound. After navigation, the account fingerprint and selected PlanetIdentity are re-read from game-owned DOM. CAPTCHA remains fail-closed through the identity reader.

## Boundary after AUTO-04

V2 can now safely switch between its own proven planets through application service `switch_owned_planet(...)`.

The user still has to manually prepare `fleets.php`, System messages and `galaxy.php`. AUTO-05 is the first stage allowed to automate those page preparations through the same coordinator/journal.