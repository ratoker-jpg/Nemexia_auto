# V2-51 — asteroid action contract audit

Date: 2026-08-08

Baseline: `c2fa01d4e441c412886fe88ff8f7aee76827f70d` (`main`, exact V2-50 handoff / PR #83).

Scope: research + pure contract + sanitized fixtures only. This PR must not scan the live game, switch a planet/system, call `squareInfo`, prepare recyclers, click SendFleet, mutate V2 SQLite, mutate legacy SQLite, add a scheduler, or add a Qt action.

## Effective legacy runtime

The default runtime is still `run_app.bat -> app_entry.py`, so the effective asteroid behavior is the base `BrowserWorker` plus installed patch layers, not an isolated historical function.

Relevant effective call sites:

- `app_entry.py` installs `install_raid_home_selection(BrowserWorker)`, whose own comment confirms asteroid/recycler flows already use `_select_planet()`;
- `app_entry.py` installs `install_asteroid_scope_ui(...)`, exposing the already-supported asteroid galaxy setting (1–3);
- base asteroid execution remains in `browser.py` (`scan_asteroids`, `_resolve_asteroid_plan`, `_send_asteroid_once`, `send_asteroid`, `run_asteroid_cycle`);
- movement math is in `asteroids.py`;
- the separate `debris_asteroids_feature.py` wraps debris-specific discovery/persistence/UI and is **not** part of the asteroid action migration batch.

The V2 migration therefore must preserve proven mechanics while intentionally dropping legacy behaviors that conflict with the V2 safety baseline.

## Browser and scan contract

### Legacy page acquisition

Legacy `_ensure_galaxy_page()` is not attach-only. It may:

1. create/select a Nemexia page;
2. switch the source planet;
3. navigate to `galaxy.php`;
4. call `_load_galaxy_system()`.

V2 must **not** copy that behavior. V2 remains attach-only after V2-50. If the required page/system is not already available, V2 must report a typed unavailable state rather than navigating or switching the account automatically.

### Galaxy system load

Legacy `_load_galaxy_system()` uses:

- `#c1` — galaxy selector/input;
- `#c2` — solar-system selector/input;
- `refreshGalaxy()` — game JS loader;
- `ajax_galaxy.php` — POST response gate;
- `#galaxyHolder` — rendered system content;
- `#galaxyLoading` — loading-state evidence;
- solar systems restricted to `1..40`.

A saved real galaxy page confirms asteroid links in `#galaxyHolder` and `squareInfo(g,s,p)` hover calls. The sanitized V2 fixture preserves only this selector/coordinate structure.

Automatic multi-system `refreshGalaxy()` scanning changes the browser's current rendered system and is therefore **not** automatically approved for V2-52. The first V2 read boundary must start from already-open/rendered evidence. Any future broad read-only scan needs an explicit contract rather than being smuggled in as a side effect of migration.

### Asteroid discovery

Legacy `_read_asteroid_links()` scans `#galaxyHolder a` and recognizes links containing an image whose `src` includes `asteroid`.

Coordinates come from either:

- link query facts `c1`, `c2`, `c3`; or
- `squareInfo(g,s,p)` in `onmouseover`.

Saved-page evidence also shows direct asteroid links of the form:

```text
fleets.php?c1=<g>&c2=<s>&c3=<p>&type=8
```

The visible name is `Астероид` for unowned asteroid cells, but **UI text is not an automation key**. V2 should prefer structured link/image/coordinate facts.

### Asteroid detail read

Legacy `_fetch_asteroid_info()` performs a read request:

```text
POST ajax_info.php
body: type=squareInfo&c1=<g>&c2=<s>&c3=<p>
```

The response is expected to contain asteroid information including:

- last movement server time;
- next movement server time;
- speed / period in minutes per field.

CAPTCHA-like response content stops the operation.

This request is read-only with respect to game state, but V2-51 does not call it. V2-52 must decide explicitly whether its attach-only reader may issue this exact read request from an already-open galaxy page; it may not navigate to produce the page first.

## Server-time contract

Saved pages label the game clock as `UTC+04:00` and expose `window.currentTime`.

Legacy asteroid math compares naive server wall-clock values with each other. V2-51 makes that implicit assumption explicit: parsed server wall-clock timestamps are interpreted as UTC+04 and normalized to UTC before comparisons.

A missing or unparseable movement timestamp is invalid evidence. V2 must not replace it with local `now`.

## Tooltip and observation contract

The effective parser requires wording equivalent to `Информация об астероиде` and both:

```text
Последнее перемещение YYYY-MM-DD HH:MM[:SS]
Следующее перемещение YYYY-MM-DD HH:MM[:SS]
```

`Скорость N Минут` is a fallback source for the period only when the difference between last/next timestamps is not positive.

If the captured `next_move` boundary is already at/before the observed server time, the effective parser advances the movement schedule by full periods while keeping the visible coordinate as the observation origin.

Minimum V2 observation provenance is therefore:

- galaxy/system/position origin;
- `last_move_at`;
- `next_move_at`;
- `period_seconds`;
- exact observation/read time;
- source/provenance marker.

There is **no accepted legacy age-based stale TTL** for asteroid observations. Legacy can reuse a saved movement schedule and predict later moves. V2 must not invent a silent TTL. A future observation is stale/invalid only when required provenance is missing or live evidence contradicts the saved asteroid/movement facts, unless a later owner decision explicitly introduces an age threshold.

## Movement contract

Asteroids move linearly through 24 positions per solar system.

Boundary examples already locked by legacy self-test:

```text
3:38:24 + 1 shift -> 3:39:1
3:39:24 + 1 shift -> 3:40:1
```

Movement beyond system 40 is invalid.

For arrival at or after the next movement boundary:

```text
shifts = 1 + floor((arrival - next_move) / period)
```

Before the next movement boundary, `shifts = 0`.

The effective legacy `_resolve_asteroid_plan()` does **not** use the configured safety buffer to shift the predicted coordinate. It predicts with safety `0`, then separately computes the distance from arrival to the nearest movement boundary and rejects the candidate when:

```text
movement_margin < configured_safety_seconds
```

V2 must preserve that distinction. Using the safety buffer to advance the target coordinate would change behavior.

## Flight-time stabilization contract

Legacy plan resolution is iterative because asteroid movement can change the correct target after the game calculates flight time.

For at most **8 iterations**:

1. select a candidate target coordinate;
2. write `#target_c1`, `#target_c2`, `#target_c3`;
3. invoke the game `FlyCheck()` calculation;
4. read `window.seconds` / `window.seconds2`;
5. read optional gas from `#missionGasNeeded`;
6. compute arrival from current server time + one-way seconds;
7. predict the asteroid coordinate at that arrival;
8. repeat until predicted coordinate equals the currently calculated candidate.

If it does not stabilize within 8 iterations, the candidate is invalid for that attempt.

These calculations are browser **preparation facts**, not permission to send.

## Recycler preparation contract

Effective legacy recycler preparation uses:

- recycler input `#ship_1_11`;
- available recycler value `#ship_1_11_max`;
- mission select `#mission` with value `8`;
- `selectMissionImg(8)`;
- `shipsCheck()`;
- transition to `#TabSendFleets`;
- source/home verification from `#my_c1/#my_c2/#my_c3`.

Legacy may switch planets and navigate to `fleets.php` before this preparation. V2 must not. Future V2 preparation requires an already-open `fleets.php` and must prove the current source equals the requested source before mutating form state.

A historical account-specific default such as `[3:39:8]` is **not** a V2 invariant and must not be hardcoded as the user's source.

## Capacity contract

Before a wave, legacy bounds the request by:

- live fleet capacity;
- available recyclers divided by recyclers-per-flight;
- requested max flights.

V2 must continue using live fleet capacity facts, not a UI-only configured slot count when better live data exists.

A single dispatch is not ready when:

- requested recyclers <= 0;
- available recyclers < requested recyclers;
- free fleet slots <= 0;
- observation/preparation facts are invalid.

These are pre-side-effect failures and must not create an ambiguous send record.

## Send endpoint and verification contract

Legacy `_send_asteroid_once()` uses:

- `#SendFleetButton`;
- a POST to `ajax_fleets.php` containing `type=SendFleet`;
- response field `pass` (`0` is explicit rejection);
- optional `info` text for game diagnostics.

The remote send must be considered accepted/uncertain once the SendFleet click/request can have reached the game. V2 cannot assume an exception after that point means no remote effect.

Verification is independent of the response body. V2 must require a **new fleet row** whose:

- fleet ID did not exist before the send;
- normalized target exactly equals the stabilized asteroid target;
- mission is exactly `Добыча газа`.

The existing table contract is:

- rows: `#fleetHandler tbody tr`;
- fleet ID: `.fleetType a` → `fleetDetails(<id>)`;
- target: second data cell;
- mission: `.fleetType a` text / mission cell.

If the game may have accepted the request but no matching new row is observed, the result is ambiguous/unverified and **must not be retried automatically**.

## Legacy retry difference — intentionally not copied

Legacy `send_asteroid()` contains a special one-time retry for the historical `Не выбраны корабли` failure after checking that no new gas-mining flight appeared.

The V2 action discipline is stricter:

- exactly one remote SendFleet attempt per immutable request identity;
- no automatic second SendFleet click;
- a proven pre-send validation/rejection may be returned as failed-safe;
- any uncertainty after a possible remote submission becomes ambiguous and blocks retry until reconciliation proves safety.

This is an intentional safety improvement, not a parity defect.

## CAPTCHA contract

CAPTCHA is checked during scan/preparation, before send and during verification. V2 behavior remains:

1. detect;
2. stop/fail closed;
3. require manual human handling in the browser;
4. never solve, click or bypass.

CAPTCHA appearing after a possible remote SendFleet attempt cannot be treated as a clean failure; without exact verification the journal must remain unresolved/ambiguous.

## Candidate budgeting contract

The effective dynamic legacy cycle uses:

```text
first batch: requested + 5
later batch: missing + 5
global candidate cap: 200
```

Coordinates are deduplicated within a cycle. Generic asteroid scanning moves the system cursor downward and does not revisit a consumed system in the same cycle.

These budgeting facts are deterministic policy and can be migrated independently of browser mutation.

## Auto-repeat contract and V2 difference

Legacy asteroid auto-renew can persist its enabled/next-cycle state and continue after process restart. That directly conflicts with the V2 scheduler safety baseline established by AutoFarm.

V2 must **not** copy restart auto-resume. If asteroid auto-repeat is eventually enabled:

- every new process starts disarmed;
- manual Start is required;
- only an already journaled/verified dispatch boundary may be used;
- pending/ambiguous asteroid side effects block the scheduler;
- CAPTCHA/live failures disarm it.

V2-51 through V2-57 do not enable auto-repeat unless a later stage explicitly proves all of those gates.

## Asteroid vs debris scope

`debris_asteroids_feature.py` adds a separate 120-system scan (galaxies 1–3, systems 40→1), marker `содержит обломки`, persistence and manual selected sends.

Those debris-specific behaviors are deliberately out of scope for V2-51→V2-58. The asteroid action boundary is migrated first; debris/recycling begins only after the asteroid parity gate.

## Typed outcomes pinned by V2-51

Read states remain distinct:

- `live_unavailable`;
- `captcha`;
- `no_asteroids`;
- `ready`.

Pre-dispatch readiness remains distinct:

- `live_unavailable`;
- `captcha`;
- `invalid_observation`;
- `capacity_blocked`;
- `ready`.

Later mutation stages must add verified/ambiguous/failed-safe action outcomes without collapsing them into UI strings.

## V2-51 code/fixture scope

This PR adds only:

- pure `v2.domain.asteroids` facts/math/classification;
- sanitized asteroid HTML/tooltip fixture;
- offline contract tests;
- this audit document/index entry.

It adds **no** Playwright/CDP backend, SQLite schema, Qt action, scheduler or game request.

## Constraints for V2-52+

V2-52 must begin with an attach-only observation source and must not navigate or switch systems/planets automatically.

Before V2-55 performs the first real asteroid SendFleet mutation, the path must already have:

1. typed command and validation;
2. explicit `actions_enabled` gate;
3. read-only preparation proving source/recyclers/observation/plan;
4. persistent immutable request identity;
5. unresolved-request idempotency;
6. journal pending written before the remote effect;
7. exactly one SendFleet attempt;
8. exact new-fleet verification;
9. conservative ambiguous handling and restart blocking.
