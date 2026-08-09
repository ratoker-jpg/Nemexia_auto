# AUTO-11 — effective legacy asteroid autorenew audit

Date: 2026-08-09

Baseline: `757903c652707e71e59d2fd14951f4985afd27ae` — squash PR #140 (`feat: add controlled persistent 3x40 discovery`), exact post-main push CI #357 green.

Scope of this document: audit the effective legacy asteroid autorenew call chain and freeze the V2 implementation contract before adding the scheduler. Debris repeat is explicitly outside AUTO-11 because the effective legacy debris workflow does not implement automatic repeat cycles.

## Decision

Effective legacy **does** implement asteroid autorenew. The accepted behavior is:

```text
explicit enable
→ run asteroid scan/send cycle
→ verify each accepted gas fleet
→ latest verified return_at + configured buffer
→ wait
→ run the next cycle
```

The V2 implementation will preserve that useful behavior but use the already-proven V2 navigation, identity and asteroid action contracts. It will not copy the legacy timer/UI/Playwright architecture.

Two deliberate safer V2 differences are required:

1. **Startup is always disarmed.** Legacy persisted `asteroid_auto_enabled` and could resume after process restart. AUTO-11 will persist diagnostic scheduler state/configuration, but a new process must not restore an armed scheduler. The user must explicitly Start again.
2. **Capacity is authoritative live game evidence.** Legacy asteroid cycle bounded work with a configured `max_slots` plus active-flight rows. V2 keeps the existing asteroid backend gate that proves `#FleetsCount`, `#MaxFleets` and `#ship_1_11_max` immediately before SendFleet.

## Effective legacy call chain

`app_entry.py` installs the effective browser/runtime patches before constructing `RaidManagerApp`. Relevant behavior is composed from `app.py`, `browser.py`, `background_browser_fix.py`, `all_flight_slots_fix.py` and the fleet-capacity patches.

### Start / arming

`RaidManagerApp.toggle_asteroid_auto()`:

- requires explicit operator confirmation;
- disables normal AutoFarm if it is enabled, so two automatic senders do not compete;
- sets `asteroid_auto_enabled`;
- clears the previous next-cycle timestamp and cancellation flag;
- saves asteroid settings;
- immediately calls `_run_asteroid_cycle(auto=True)`.

Legacy source defaults are separate asteroid settings (`asteroid_home_*`, historically defaulting to `3:39:8`), not the farm planet. The source is reselected before galaxy/fleet work.

### Cycle demand and fleet capacity

`BrowserWorker._run_dynamic_asteroid_cycle()`:

1. CAPTCHA check.
2. `sync_all_flights()` to count all own active missions occupying shared fleet slots.
3. `available_recyclers(home)` from recycler ship field.
4. `requested = min(max_flights, free_slots, available_recyclers // recycler_count)`.
5. If requested is zero, return a capacity error and the application stops autorenew.

Legacy `free_slots` used the configured `max_slots` value. AUTO-11 intentionally uses the stronger existing V2 live `FleetsCount / MaxFleets` proof instead.

### Asteroid discovery and target selection

Legacy scan:

- reselects the asteroid source planet;
- opens/prepares galaxy;
- scans configured systems downward;
- reads visible asteroid coordinates;
- reads `ajax_info.php` with `type=squareInfo`;
- parses last/next movement time and movement period;
- skips non-CAPTCHA malformed candidates and continues;
- stops hard on CAPTCHA.

For each candidate, `_resolve_asteroid_plan()` repeatedly asks the game for live flight time, predicts where the asteroid will be at arrival, and iterates until the target stabilizes. It also enforces the configured movement-boundary safety margin.

AUTO-11 uses V2-owned asteroid evidence. Each automatic cycle refreshes evidence through the AUTO-09/AUTO-10 NavigationCoordinator-owned galaxy reader before any SendFleet request. A typed short-lived live-evidence proof bridges that verified galaxy read to the existing fleets-page action backend; manual callers without such proof retain the older direct galaxy re-check requirement.

### Recycler composition and mission

Effective legacy uses:

- recycler ship field `#ship_1_11` / availability `#ship_1_11_max`;
- mission code `8` (`Добыча газа`);
- configured recycler count per flight;
- a freshly calculated target/flight time immediately before each send.

AUTO-11 does not create another SendFleet implementation. It calls the existing `AsteroidRequestCoordinator → AsteroidActionService → V2AsteroidCdpBackend` path.

### Exactly-once / ambiguous SendFleet

Legacy already stopped autorenew when the game might have accepted SendFleet but a new exact gas-flight row could not be proven. It contained a special one-time retry only for a known pre-send "no ships selected" rejection after checking that no new gas mission appeared.

V2 is deliberately stricter:

- immutable request ID;
- persistent pending row before the remote effect;
- exactly one SendFleet click per request;
- exact source/target/mission/fleet verification;
- any accepted-but-unverified or unclassified post-pending failure becomes `ambiguous`;
- **no automatic retry after ambiguous** and no restoration of the legacy special send retry.

Any unresolved asteroid action blocks a later scheduler remote attempt until reconciled manually/recovery logic resolves it.

### Return timing and next cycle

Legacy `_schedule_next_asteroid_cycle(results)` computes:

```text
next_cycle_at = max(all verified result return_at) + asteroid_cycle_buffer_minutes
```

Default buffer: 5 minutes.

`_tick()` runs once per second and starts the next asteroid cycle when `next_cycle_at <= now` and the application is not busy.

AUTO-11 preserves `latest verified return_at + buffer` as the scheduling rule. Only verified V2 dispatch results contribute to `next_cycle_at`.

### No asteroid / insufficient valid candidates

Legacy:

- no asteroid observations → `no_asteroids` error → autorenew stops;
- some sends but insufficient valid candidates to satisfy the capacity-bounded requested wave → `not_enough_valid` error → autorenew stops;
- capacity zero at cycle start → error → autorenew stops.

AUTO-11 keeps fail-closed semantics. It does not create an endless periodic scan when a cycle cannot produce the required safe work.

### CAPTCHA

Legacy checks CAPTCHA during page preparation/scanning/send and also polls for it while waiting between cycles (about every 20 seconds). Detection disables asteroid autorenew and requires manual handling.

AUTO-11 contract:

- CAPTCHA = hard STOP;
- never solve/click/bypass;
- scheduler is disarmed;
- no automatic resume after manual CAPTCHA completion; user explicitly Starts again.

### Browser failure / tab loss

Legacy treats serious browser/cycle exceptions as errors and disables autorenew. Its background patch makes minimized operation possible but does not provide the persistent identity/recovery guarantees of V2.

AUTO-11 fails closed on Browser Readiness or NavigationCoordinator errors. AUTO-13 owns explicit browser/session recovery; AUTO-11 must not silently reconnect or transform uncertainty into another remote attempt.

### Stop

Legacy cancellation sets a cancellation event and checks it during scan and between candidate sends. An already-started remote request is allowed to finish; cancellation prevents the next side effect.

AUTO-11 preserves this rule: Stop disarms future attempts immediately and is checked between discovery steps and candidate sends. It never cancels an in-flight SendFleet in a way that would reopen a duplicate-send window.

### Restart

Legacy persisted `asteroid_auto_enabled` plus `asteroid_next_cycle_at`, so `_tick()` could continue after restart.

AUTO-11 intentionally changes this: persisted state is diagnostic/recovery evidence only. Service construction converts any stale armed state to `disarmed_restart`; no browser mutation or SendFleet can occur until a new explicit Start.

### Manual planet/page interference

Legacy repeatedly reselected the source planet, but verified primarily coordinate/host facts and had no account/context journal.

AUTO-11 requires:

- source coordinate must belong to the proven AccountContext/PlanetIdentity set;
- source PlanetIdentity/account fingerprint is captured when Start is accepted;
- unresolved NavigationCoordinator journal blocks any new browser mutation;
- before each discovery/send phase, source/account/page context is re-proven through Browser Readiness/NavigationCoordinator;
- unexpected account/planet/page changes fail closed.

AUTO-13 will add the broader interference/recovery reconciliation matrix.

## AUTO-11 typed state machine

Persistent states are diagnostic; only the in-process explicit Start may arm execution.

```text
DISARMED
  → RUNNING_DISCOVERY      explicit Start or due tick
RUNNING_DISCOVERY
  → RUNNING_DISPATCH       complete current evidence + candidates
  → STOPPED_NO_ASTEROIDS   no usable current evidence
  → BLOCKED                navigation/browser/context failure
RUNNING_DISPATCH
  → WAITING_RETURN         verified wave; latest return + buffer stored
  → STOPPED_CAPACITY       zero safe capacity before any send
  → STOPPED_INSUFFICIENT   candidate set exhausted before requested work
  → STOPPED_CAPTCHA        CAPTCHA
  → STOPPED_AMBIGUOUS      unresolved/ambiguous asteroid mutation
  → BLOCKED                other fail-closed error
WAITING_RETURN
  → RUNNING_DISCOVERY      due time reached while still explicitly armed
any armed state
  → DISARMED               explicit Stop
process restart
  → DISARMED_RESTART       always; never auto-arm
```

## Required V2 orchestration

For every automatic cycle:

1. Confirm scheduler is explicitly armed in this process.
2. Reject if any NavigationCoordinator journal row is pending/ambiguous **before any readiness mutation**.
3. Reject if any asteroid action is pending/ambiguous before the cycle can reach another remote send.
4. Prove source AccountContext + PlanetIdentity.
5. Refresh asteroid evidence using NavigationCoordinator/AUTO-10 owned galaxy traversal/read boundaries.
6. Build deterministic candidates only from the refreshed V2-owned evidence for this cycle.
7. For each candidate, re-prove its current galaxy/system and read exact current squareInfo evidence.
8. Prepare `fleets.php` on the same proven source through Browser Readiness.
9. Pass the typed short-lived live evidence to the **existing** asteroid action journal/backend.
10. Existing backend proves authoritative recyclers/capacity, source, mission, fleet composition, target freshness and performs exactly one SendFleet.
11. After each verified send, re-observe account/source context before allowing a later candidate.
12. Stop immediately on CAPTCHA, ambiguity, unresolved journals, context loss, manual Stop or serious browser error.
13. Schedule only from verified result `return_at` values.

## Explicit exclusions

- No debris autorenew/repeat.
- No common "repeat everything" scheduler.
- No second SendFleet implementation.
- No Qt Playwright/CDP/selectors.
- No CAPTCHA interaction.
- No silent CDP reconnect/rebind after an established mutation session is lost.
- No automatic restart re-arm.

## Acceptance for AUTO-11

- explicit Start; process startup disarmed;
- Stop prevents later scheduler attempts;
- deterministic persistent status/config/next-cycle evidence;
- current-cycle V2-owned asteroid evidence only;
- authoritative live fleet capacity/recycler proof;
- central NavigationCoordinator/Browser Readiness for page/planet/system mutations;
- exactly-one existing asteroid action journal/backend reused;
- no retry after ambiguous;
- unresolved navigation/action blocks new effects;
- CAPTCHA hard STOP;
- restart cannot duplicate a send;
- no debris repeat;
- automation and UI remain separate PR scopes.
