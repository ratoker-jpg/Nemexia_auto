# V2-50 — raid-loop parity gate

Date: 2026-08-08

Implementation baseline under audit: `79f81e4b4776049d8ffaf0a3b6850885fb1db01f` (`main`, V2-49 / PR #81).

Scope: parity verification and documentation only. No new game-side effect is introduced here.

## Completed fresh-recon batch

| Stage | PR | Squash SHA | Result |
| --- | ---: | --- | --- |
| V2-41 | #73 | `9ec965bf92bf4ef54746640a5a9433084813005a` | spy/report contract audit + sanitized fixtures |
| V2-42 | #74 | `735331642fb967d6f4667e603eb9d6d1033fcdd1` | attach-only report/freshness reader |
| V2-43 | #75 | `57347ee6e87e51bfcaed6ac60ad2f71e3ef40c79` | typed spy action boundary |
| V2-44 | #76 | `e02418348beb1ee9240b0c30fa7afaaf92cc0dbd` | persistent spy journal/idempotency |
| V2-45 | #77 | `3df7cd5fec03a6b2a04b032591f95374987d040f` | one-shot exact-fleet verified fresh spy acquisition |
| V2-46 | #78 | `334442e7ee1345079ea4aaf241bbca322d34ba7d` | V2-owned recon/target ingestion |
| V2-47 | #79 | `9463b8fda33819ad8a22e076c001e86f98c5e3e5` | deterministic queue builder/refill |
| V2-48 | #80 | `134f50626963c50eed9ac323da248da2d0d0613c` | controlled recon → verified ingest → refill |
| V2-49 | #81 | `79f81e4b4776049d8ffaf0a3b6850885fb1db01f` | continuous-cycle recovery/hardening |

Every listed stage was merged only after the required Windows/PySide6 CI gate and then re-verified by push-CI on its exact squash SHA.

## Parity result

The V2 raid loop now owns the mutation and decision path needed to recover an exhausted raid queue from a fresh verified spy report without calling legacy mutation code.

The safe V2 path is:

1. explicit global `actions_enabled` gate;
2. explicit in-session AutoFarm arm; a new process always starts disarmed;
3. live attach-only fleet/capacity read;
4. V2-owned queue and typed `need_recon` state when it is exhausted;
5. user-supplied exact existing espionage `fleet_id` for the current session only;
6. read-only preparation proving exact DOM source/target + available rendered report source;
7. persistent immutable spy request ID before mutation;
8. exactly one `processSpy(fleet_id)` attempt;
9. verification by a new report ID + exact target + fresh timestamp;
10. ingestion of only the exact verified fresh report into V2-owned recon storage;
11. deterministic AutoFarm queue policy over V2-owned target/report facts;
12. refill only after verified acquisition;
13. raid dispatch through the existing persistent raid journal and exactly-one-attempt SendFleet boundary;
14. safety stop on any unresolved/ambiguous raid or spy side effect.

No UI status string controls this flow; decisions are made from typed states/results and persisted journal fields.

## Accepted legacy contracts preserved

### Report freshness

Nemexia report wall-clock remains interpreted as server UTC+04 and normalized to UTC. Default freshness remains 24 hours. Missing timestamps are never replaced with `now`.

### Queue eligibility

The policies remain separate:

- manual metal queue: metal `>= 480,000` after target-level filters;
- manual mineral queue: reported mineral value is sufficient; no 500k threshold;
- AutoFarm: minerals `>= 500,000`, ranked by minerals desc, metal desc, coordinate.

### Successful empty scan

`fresh report evidence exists + eligible AutoFarm targets = 0` is a successful empty scan and receives exactly 25 minutes of no-target cooldown.

That cooldown is V2-owned, persisted, and separate from attack return-buffer state. Restart during the cooldown does not open a new spy mutation window.

`no fresh reports`, stale-only evidence, CAPTCHA, live/browser unavailability, exact-report mismatch, or ambiguous spy effect are errors/stops and do not receive the 25-minute successful-empty result.

### Raid sending

A raid mutation still requires typed validation, global action gate, persistent request identity before the side effect, one SendFleet attempt, exact live verification, and conservative ambiguous handling. Automatic retry after an ambiguous side effect remains forbidden.

### Continuous mode

Continuous AutoFarm is still an explicitly armed in-process state. Neither scheduler arm nor the exact recon fleet ID is persisted. Restart always requires a new manual Start and a new exact fleet-ID choice.

While armed, the scheduler may recover `need_recon` only through the same journaled exact-fleet boundary. It never guesses or automatically selects a spy fleet. Pending/ambiguous raid **or spy** journals block the loop globally.

## Intentional safety differences from legacy

These are not parity defects:

- V2 does not call bulk `processSpy(0)`; it processes one exact proven fleet ID at a time.
- V2 does not delete spy/system messages before refreshing reports.
- V2 does not create browser tabs or navigate to `fleets.php` / `options.php` automatically.
- V2 does not solve, click, or bypass CAPTCHA.
- V2 does not automatically retry an ambiguous remote mutation.
- Legacy SQLite remains read-only and is never the mutable runtime queue/recon store for V2.

## Remaining raid-loop limitations

The raid loop is self-contained with respect to **V2 mutation code**, but live browser prerequisites remain explicit:

- an already-open `fleets.php` page is required;
- the System messages area on `options.php` must already be rendered for report verification;
- continuous recon recovery requires a user-supplied exact existing espionage fleet ID for that session;
- V2 does not yet create a brand-new espionage route when no processable spy-fleet row exists;
- pending/ambiguous spy actions stay blocking unless later proven/resolved; they are never retried automatically.

These limits are safer than inferring a route or browser action that has not been proven by the current contract.

## Storage / UI state

V2-owned SQLite is schema version 6 and contains:

- typed settings;
- `raid_actions`;
- `raid_queue`;
- `spy_actions`;
- `recon_targets`;
- immutable `recon_reports`.

Legacy SQLite remains `mode=ro` + `PRAGMA query_only=ON`.

The default launcher remains Tkinter (`run_app.bat -> app_entry.py`). PySide6 remains opt-in via `app_qt.py`; final cutover is not part of this batch.

## Deferred work after V2-50

Per the accepted batch order, next action migration is:

1. asteroid execution / auto-repeat;
2. debris/recycling execution.

Still deferred:

- automatic message deletion;
- automatic CAPTCHA interaction;
- unattended browser launch/navigation;
- default Tkinter → Qt cutover;
- deletion of legacy Tkinter/patch modules.

## V2-50 gate

This PR adds a source-level parity invariant test and updates the current-state handoff. Full CI must be green on the final code+docs head before merge.

Because a squash SHA does not exist until GitHub performs the squash merge, the exact V2-50 squash SHA will be pinned immediately afterward in a tiny docs-only handoff PR, before any asteroid implementation branch is started. This mirrors the previous post-batch handoff discipline and avoids inventing a future SHA.
