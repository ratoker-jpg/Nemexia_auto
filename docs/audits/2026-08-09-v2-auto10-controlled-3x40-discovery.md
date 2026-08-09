# AUTO-10 — controlled automatic 3×40 discovery

Date: 2026-08-09

Baseline: `49626e26e255a6864db0b2f677275cde5853c5e6` (AUTO-09 squash PR #139, exact post-main CI #347 green).

## Goal

Restore the effective legacy asteroid/debris discovery traversal without reintroducing independent browser ownership or unsafe loop semantics.

The exact traversal is:

```text
galaxy 1: systems 40 → 1
galaxy 2: systems 40 → 1
galaxy 3: systems 40 → 1
```

Total: **120 verified systems**.

## Persistent scan contract

AUTO-10 is a V2-owned persistent stepper, not a fire-and-forget browser loop.

`discovery_scans` stores:

- immutable `scan_id`;
- status;
- cursor index;
- account fingerprint;
- selected PlanetIdentity (`planet_id` + coord);
- created/updated/completed timestamps;
- stop/failure detail.

`discovery_scan_systems` stores one committed evidence row per deterministic sequence index and exact galaxy/system.

States:

```text
running
stopped
completed
ambiguous
failed_safe
```

Only `completed` with cursor `120` and exactly 120 committed system rows may become `last_completed`.

An incomplete/stopped/failed/ambiguous scan never replaces the previous completed scan.

## Per-system sequence

One step performs:

```text
read persistent cursor
→ assert no unresolved navigation effect
→ verify same account + same selected PlanetIdentity + ready galaxy page
→ AUTO-09 navigate_galaxy_system with a fresh immutable request ID
→ require VERIFIED
→ re-observe same page/account/planet + exact requested galaxy/system
→ read asteroid/debris evidence from that same owned page
→ require all visible asteroid squareInfo reads to succeed
→ persist asteroid/debris observations
→ persist system evidence
→ advance cursor by exactly one
```

The cursor advances only after the full system step succeeds.

## One browser owner

Traversal does not use the older independent read-only CDP owners.

`OwnedDiscoveryReadMixin` is installed on the same guarded backend instance already used by:

- NavigationCoordinator;
- AUTO-07 exact-fleet reconnaissance;
- AUTO-09 verified galaxy/system navigation.

The reader validates the expected account, PlanetIdentity and exact rendered galaxy/system before reading anything.

## System evidence

For the already-rendered system, AUTO-10 reads:

- `#galaxyHolder`;
- exact `#c1` / `#c2` values;
- server `currentTime`;
- every visible asteroid coordinate;
- read-only `ajax_info.php` `squareInfo` evidence for each visible asteroid.

The existing asteroid and debris parsers remain authoritative for domain facts.

A system is complete only when every visible asteroid has readable squareInfo evidence:

```text
visible_asteroids == readable_square_info
```

Any missing/failed squareInfo read stops the scan before cursor advance. It is never interpreted as `no_debris` or an empty system.

## Restart/idempotency

The persistent cursor survives process restart.

If a crash happens before the cursor commit, the same sequence index remains pending. Existing unresolved navigation evidence blocks automatic continuation. If navigation was already verified and the page is still on that exact system, AUTO-09 can verify the same destination without another remote effect.

Debris persistence already deduplicates exact observation identities. AUTO-10 adds exact asteroid-observation dedupe before append so replaying an uncommitted cursor after a crash does not multiply identical facts.

`ambiguous` scans cannot auto-resume. `stopped` and `failed_safe` scans may resume only after the application has restored the original account/planet on a verified galaxy page and there is no unresolved navigation effect.

## Start / Stop

The application context exposes typed operations:

```text
start_discovery_scan
stop_discovery_scan
resume_discovery_scan
step_discovery_scan
run_discovery_scan
last_completed_discovery_scan
```

The automation PR contains no Qt changes. A separate UI-only follow-up will expose explicit Start/Stop/progress controls and drive the stepper through application services only.

## Safety

- CAPTCHA = STOP through the shared browser evidence boundary.
- No CAPTCHA solve/click/bypass.
- One AUTO-09 remote navigation attempt per system request.
- No automatic retry after ambiguous navigation.
- No cursor advance after ambiguity, context mismatch, read failure or partial system evidence.
- Legacy SQLite remains read-only.
- Discovery schema is separately versioned in V2 storage.
- No UI browser selectors.
- No independent hidden browser tab/page owner.

## Scope

AUTO-10 performs discovery only.

It does not add:

- asteroid dispatch/repeat scheduling;
- debris repeat;
- Rest Mode;
- mutation-session recovery/rebind;
- navigation/UI consolidation.

AUTO-11 owns repeat parity and must preserve the AUTO-01 result: asteroid autorenew is proven; debris repeat is not.

## Acceptance

AUTO-10 is complete when:

1. sequence is exactly 3×40 / 120 systems;
2. persistent cursor survives restart;
3. one system step uses AUTO-09 verified navigation;
4. traversal reads evidence from the same owned page;
5. partial squareInfo evidence cannot advance cursor or claim empty/debris-free state;
6. incomplete scan cannot replace `last_completed`;
7. ambiguous navigation blocks continuation without retry;
8. asteroid/debris facts persist into V2-owned storage;
9. full CI is green;
10. substantive P1/P2 review findings are resolved;
11. squash merge is followed by exact green post-main push CI.

After the automation gate, add the separate UI-only Start/Stop/progress surface, then proceed to AUTO-11.
