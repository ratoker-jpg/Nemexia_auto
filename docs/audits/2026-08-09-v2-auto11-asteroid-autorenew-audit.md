# AUTO-11 — effective legacy asteroid autorenew audit

Date: 2026-08-09

Baseline: `757903c652707e71e59d2fd14951f4985afd27ae` — squash PR #140 (`feat: add controlled persistent 3x40 discovery`), exact post-main push CI #357 green.

Scope: freeze the effective legacy asteroid autorenew call chain and the safer V2 replacement contract before merge. Debris repeat is explicitly outside AUTO-11 because effective legacy does not implement it.

## Decision

Effective legacy **does** implement asteroid autorenew:

```text
explicit enable
→ asteroid scan/send cycle
→ verified gas flights
→ latest verified return_at + buffer
→ wait
→ next cycle
```

AUTO-11 restores that behavior on top of V2 identity/navigation/discovery/action contracts. It does not copy the legacy timer, Tkinter callbacks or browser monkey-patch architecture.

Two deliberate safer V2 differences are required:

1. **Startup is always disarmed.** Legacy persisted `asteroid_auto_enabled` and could continue after process restart. V2 persists diagnostic state/configuration but never restores authority to send. A new process requires a new explicit Start.
2. **Capacity is authoritative live game evidence.** Legacy bounded the asteroid cycle with configured `max_slots` plus active-flight rows. V2 retains the existing action backend proof of `#FleetsCount`, `#MaxFleets` and `#ship_1_11_max` immediately before SendFleet.

## Effective legacy call chain

`app_entry.py` installs the effective browser/runtime patches before constructing `RaidManagerApp`. Relevant behavior is composed from `app.py`, `browser.py`, `background_browser_fix.py`, `all_flight_slots_fix.py` and fleet-capacity patches.

### Start / arming

`RaidManagerApp.toggle_asteroid_auto()`:

- requires explicit operator confirmation;
- disables normal AutoFarm so two automatic senders do not compete;
- sets `asteroid_auto_enabled`;
- clears the previous next-cycle timestamp/cancel flag;
- saves asteroid settings;
- immediately invokes `_run_asteroid_cycle(auto=True)`.

Legacy uses separate asteroid source settings (`asteroid_home_*`, historically default `3:39:8`). The source planet is reselected before galaxy/fleet work.

### Need for another wave / capacity

`BrowserWorker._run_dynamic_asteroid_cycle()`:

1. checks CAPTCHA;
2. reads all own active flights because Nemexia has one shared fleet-slot limit;
3. reads available recyclers;
4. computes `requested = min(max_flights, free_slots, available_recyclers // recycler_count)`;
5. zero requested work is an error and autorenew stops.

AUTO-11 preserves capacity-bounded work but uses the stronger existing V2 live game counters instead of trusting a configured maximum.

### Asteroid discovery and target

Legacy:

- reselects source planet;
- prepares galaxy;
- scans systems downward;
- reads visible asteroid coordinates;
- POSTs `ajax_info.php` with `type=squareInfo` and explicit `c1/c2/c3`;
- parses movement schedule;
- stops on CAPTCHA;
- skips ordinary malformed candidates and continues.

`_resolve_asteroid_plan()` repeatedly uses live game flight timing, predicts the arrival coordinate and iterates until the asteroid target stabilizes. A configured movement-boundary safety margin is required.

AUTO-11 refreshes the candidate set through the already-owned AUTO-09/AUTO-10 3×40 discovery path. Only observations added by the current completed autorenew discovery pass become that cycle's candidate snapshot. Before a candidate can send, AUTO-11 navigates to its predicted current system and performs another complete owned current-system read.

### Independent pre-send trajectory re-check without a second tab

The original V2 asteroid action backend was attach-only and `_matching_galaxy_page()` therefore expected a simultaneously open matching `galaxy.php` tab. That was a pre-AUTO-03 browser-preparation limitation, not a SendFleet requirement.

The actual trajectory re-check does not need galaxy DOM. `_read_square_info()` needs only:

- an authenticated same-origin Nemexia page;
- `window.currentTime`;
- explicit `c1/c2/c3` in the read-only `ajax_info.php type=squareInfo` request.

AUTO-11 therefore subclasses the **existing** asteroid backend only to provide the already NavigationCoordinator-prepared `fleets.php` page as that same-origin read surface. The inherited `_recheck_observation()` still executes and validates movement period/schedule immediately before preparation and again before dispatch. The inherited SendFleet implementation is untouched.

This removes the user's old manual requirement to keep a second matching galaxy tab open without introducing a second hidden page or another remote mutation path.

### Recycler composition and mission

Effective legacy and V2 both use:

- recycler ship `ship_1_11`;
- mission code `8` (`Добыча газа`);
- configured recycler count per flight;
- freshly calculated game flight timing and deterministic arrival target.

AUTO-11 calls the existing:

```text
AsteroidRequestCoordinator
→ AsteroidActionService
→ V2AsteroidCdpBackend
```

No second SendFleet implementation exists.

### Exactly-one / ambiguous SendFleet

Legacy stopped autorenew if SendFleet might have been accepted but the new exact gas-flight row could not be proven. Legacy also contained a special retry for one positively identified pre-send rejection.

V2 is stricter:

- immutable request ID;
- persistent pending row before remote effect;
- exactly one SendFleet click per request;
- final source/target/mission/ship/capacity proof;
- exact new source/target gas-flight verification;
- accepted-but-unverified or unclassified post-pending failure → `ambiguous`;
- **no automatic retry after ambiguous**;
- repository-wide pending/ambiguous asteroid action blocks later scheduler sends.

AUTO-11 uses a deterministic request identity for each session/scan/candidate. If execution fails after the action journal already records `verified`, a later tick recognizes that same immutable verified request and advances without another SendFleet.

### Return timing / cooldown

Legacy `_schedule_next_asteroid_cycle(results)`:

```text
next_cycle_at = max(all verified result return_at) + asteroid_cycle_buffer_minutes
```

Default buffer is 5 minutes. `_tick()` starts the next cycle when the deadline is due and the application is not busy.

AUTO-11 preserves exactly `latest verified return_at + buffer`; only verified V2 action results contribute.

### No asteroid / insufficient valid candidates

Legacy:

- no observations → `no_asteroids` → stop autorenew;
- some sends but insufficient safe/valid candidates for requested work → `not_enough_valid` → stop;
- zero initial capacity → stop.

AUTO-11 remains fail-closed. It does not invent an endless empty scan loop.

### CAPTCHA

Legacy checks CAPTCHA during page work and send, and about every 20 seconds while waiting between cycles.

AUTO-11:

- CAPTCHA = hard STOP;
- never solve/click/bypass;
- waiting state probes the existing fleets-page backend at the same approximately 20-second cadence when scheduler ticks are supplied;
- after CAPTCHA is handled manually, the scheduler remains disarmed until explicit Start.

### Browser failure / tab loss

Legacy serious browser/cycle errors disable autorenew. Background patches make minimized legacy operation practical but do not provide V2 persistent identity guarantees.

AUTO-11 fails closed on Browser Readiness/NavigationCoordinator/action-backend loss. `_NoAutoReconnectMixin` remains authoritative after an established mutation session is lost. AUTO-13 owns explicit browser/session recovery.

### Stop

Legacy cancellation is checked during scanning and between candidate sends; it does not cancel an already-started remote request in a way that could create a duplicate window.

AUTO-11 uses a step scheduler: one `tick()` performs at most one discovery-system step or one candidate dispatch. Explicit Stop disarms later ticks and stops a currently journaled discovery scan before future effects. An already-started immutable SendFleet is resolved only by its action journal outcome.

### Restart

Legacy can persist armed=true and `asteroid_next_cycle_at` and continue after restart.

AUTO-11 intentionally does not. `AsteroidAutorenewRepository.disarm_on_startup()` converts stale persisted authority to `disarmed_restart`; no browser mutation happens from that state.

### Planet/account/page interference

Legacy repeatedly reselected source coordinates but had no persistent AccountContext/PlanetIdentity journal.

AUTO-11 requires:

- requested source belongs to the proven owned PlanetIdentity set before Start is accepted;
- session captures source internal planet ID + coordinate + account fingerprint;
- unresolved navigation is checked **before** Browser Readiness may switch planet/page;
- every phase re-proves expected account/source/page;
- each candidate re-proves exact galaxy/system before the complete current-system read;
- after a verified send, account/source context is checked again before any later candidate;
- unexpected changes stop future sends.

AUTO-13 will expand this into the complete recovery/interference matrix.

## Typed state machine

Persistent state is diagnostic/recovery evidence; only the current process's explicit Start arms it.

```text
DISARMED / DISARMED_RESTART
  → ARMED_DUE             explicit Start
ARMED_DUE
  → RUNNING_DISCOVERY     safe source + galaxy preparation, new persistent scan
RUNNING_DISCOVERY
  → RUNNING_DISCOVERY     one verified system per tick
  → RUNNING_DISPATCH      completed current scan + candidates
  → STOPPED_NO_ASTEROIDS  no current usable evidence
  → BLOCKED/AMBIGUOUS     failed/uncertain navigation/read
RUNNING_DISPATCH
  → RUNNING_DISPATCH      one candidate result per tick
  → WAITING_RETURN        verified capacity-bounded wave
  → STOPPED_CAPACITY      no capacity before any verified send
  → STOPPED_INSUFFICIENT  candidates exhausted before requested work
  → STOPPED_CAPTCHA
  → STOPPED_AMBIGUOUS
  → BLOCKED
WAITING_RETURN
  → ARMED_DUE             latest return + buffer elapsed
any armed state
  → STOPPED_MANUAL        explicit Stop
process restart
  → DISARMED_RESTART      always
```

## Required V2 orchestration

For every cycle:

1. Confirm explicit in-process armed state.
2. Reject unresolved NavigationCoordinator journal **before any readiness mutation**.
3. Reject repository-wide unresolved asteroid action before another SendFleet.
4. Prove source AccountContext + PlanetIdentity.
5. Refresh current evidence via AUTO-10 controlled 3×40 discovery.
6. Build deterministic candidates only from observations newly written by that discovery pass.
7. Re-prove candidate current galaxy/system and read complete current squareInfo evidence.
8. Prepare the same proven source as `fleets.php` through Browser Readiness.
9. Existing asteroid backend independently repeats read-only squareInfo schedule verification from the authenticated fleets page.
10. Existing backend proves live recycler count/capacity, source, mission, target freshness and performs exactly one SendFleet.
11. Re-observe account/source after every verified action before permitting a later candidate.
12. Stop on CAPTCHA, ambiguity, unresolved journals, context loss, manual Stop or serious browser error.
13. Schedule only from verified return times.

## Explicit exclusions

- No debris autorenew/repeat.
- No common "repeat everything" scheduler.
- No second SendFleet implementation.
- No second hidden galaxy tab/page.
- No Qt Playwright/CDP/selectors.
- No CAPTCHA interaction.
- No silent reconnect after established mutation-session loss.
- No automatic restart re-arm.

## Acceptance

- explicit Start; startup disarmed;
- Stop prevents future scheduler attempts;
- typed persistent status/config/next-cycle evidence;
- one scheduler tick has at most one discovery-system step or one candidate send;
- current-cycle V2-owned asteroid evidence only;
- authoritative live capacity/recycler proof;
- NavigationCoordinator/Browser Readiness owns page/planet/system mutations;
- existing asteroid action journal/backend is the only SendFleet path;
- deterministic request recovery prevents duplicate send after a verified action;
- no retry after ambiguous;
- unresolved navigation/action blocks new effects;
- CAPTCHA hard STOP;
- restart cannot duplicate or auto-resume;
- no debris repeat;
- automation and UI remain separate PR scopes.
