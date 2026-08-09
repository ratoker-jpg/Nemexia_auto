# AUTO-02 — BrowserSession / AccountContext / PlanetIdentity

Date: 2026-08-09

Baseline: `fedd58ba9e6f7fe9c7f950489d54117d4e7362af` (AUTO-01 squash PR #128).

## Scope

AUTO-02 introduces only **typed, read-only identity evidence**. It does not navigate, create tabs, switch planets, invoke `refreshGalaxy`, process spy fleets, send fleets or change SQLite.

## Contracts

`BrowserSession` records the observed CDP endpoint, current Nemexia page URL/server and page counts. It is an observation only; exact bound-tab ownership is intentionally deferred to AUTO-03.

`AccountContext` does not fabricate a player ID that the supplied browser evidence does not prove. Its first stable ownership token is a deterministic SHA-256 fingerprint over:

```text
server host + sorted internal planet ID / coordinate pairs
```

Changing the observed owned-planet set therefore changes account ownership evidence and must invalidate later prepared navigation intents.

`PlanetIdentity` stores:

- internal planet ID from `change_planet.php?id=<planet_id>`;
- coordinate;
- display name;
- selected flag;
- selected proof from `li.active`, `#planetSwitch`, or both;
- server host;
- account ownership fingerprint;
- ownership evidence source.

The builder fails closed on duplicate IDs/coordinates, malformed IDs/coordinates, multiple active rows, a trigger outside the owned list, or disagreement between `li.active` and `#planetSwitch`.

## Runtime extraction

`ReadOnlyAccountCdpBackend` now reads the full own-planet selector from an already-open fleets page and exposes `browser_identity()`.

It remains attach-only. The AUTO-02 source contains no `goto`, click/fill/select, new page, `refreshGalaxy`, `processSpy` or `SendFleet` mutation path.

`V2BrowserFlightSource` exposes the typed identity while retaining coordinate-only `owned_planets()` compatibility for existing application/domain services.

## Boundary after AUTO-02

The old NO NAVIGATION mutation boundary still applies.

AUTO-02 proves **who/where** the browser appears to belong to. It does not yet own navigation. AUTO-03 must add one shared NavigationCoordinator, exact runtime page ownership, mutex and persistent context journal before any V2 `change_planet.php` or page-preparation mutation is permitted.
