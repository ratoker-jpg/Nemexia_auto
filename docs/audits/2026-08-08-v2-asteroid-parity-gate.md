# V2-58 — asteroid recovery / parity gate

Date: 2026-08-08

Baseline before V2-58: `6dfdc304fb440634d2d5125a676aa9831a4a7350` / PR #90 / V2-57.

Scope: recovery and parity hardening only. This gate does **not** add asteroid auto-repeat, an asteroid scheduler, automatic browser navigation, debris/recycling execution, message deletion, or CAPTCHA interaction.

## Result

The manually controlled V2 asteroid path is safe enough to close the V2-51→V2-58 asteroid action migration batch and begin a separate debris/recycling contract batch after the exact V2-58 squash SHA and push-CI are recorded.

The supported path is now:

```text
already-open galaxy.php
→ attach-only asteroid observation
→ immutable V2-owned observation evidence
→ deterministic candidate projection
→ explicit typed selection
→ read-only preparation
→ explicit operator confirmation
→ persistent pending request identity
→ fresh live trajectory/capacity/safety re-check
→ exactly one SendFleet attempt
→ exact new-flight verification
→ verified / ambiguous / failed-safe journal state
```

No automatic retry is introduced anywhere in that path.

## Recovery / parity matrix

| Case | Contract / evidence | Required outcome |
| --- | --- | --- |
| Restart with `pending` request | `tests/test_v2_asteroid_parity_gate.py::test_pending_crash_window_survives_restart_and_blocks_duplicate_side_effect` | durable `pending` survives restart; same unresolved trajectory is blocked before a second dispatch |
| Restart with `ambiguous` request | `tests/test_v2_asteroid_journal_review.py::test_timezone_equivalent_trajectory_cannot_bypass_unresolved_identity` | canonical unresolved identity survives restart and blocks retry, including timezone-equivalent evidence |
| Asteroid moved / target became stale before send | `V2AsteroidCdpBackend._validated_pre_click_snapshot` + `tests/test_v2_asteroid_dispatch_backend.py` | exact trajectory and predicted target are revalidated immediately before SendFleet; changed target/margin fails closed |
| Insufficient recyclers | `AsteroidActionService` + final pre-click snapshot | preparation rejects insufficient recycler inventory; final snapshot also rejects changed fleet composition |
| Full fleet capacity | `AsteroidActionService` + `#FleetsCount/#MaxFleets` final snapshot | zero free slot rejects before side effect; capacity is checked again immediately before SendFleet |
| CAPTCHA before side effect | prepare/final pre-click CAPTCHA checks | fail closed with no SendFleet attempt |
| CAPTCHA after potential acceptance | verification loop in `cdp_asteroid_backend.py` | stop verification and return `AsteroidDispatchAmbiguous`; never infer safe failure and never retry |
| Duplicate candidate evidence | schema-v8 `asteroid_observations` unique identity + deterministic candidate projection | exact evidence is idempotent; multiple proven observations may remain for provenance while current candidate view deduplicates deterministically |
| Duplicate dispatch identity | partial unique unresolved index `idx_asteroid_actions_unresolved_identity` | `pending`/`ambiguous` exact trajectory blocks another remote attempt |
| Manual stop | V2-58 `STOPPED_MANUAL` + Qt Stop button | stop is checked **between** candidate side effects; an already-started remote attempt is never cancelled mid-flight and must settle verified/ambiguous before the next candidate can be considered |
| Exact new-flight verification | `select_verified_asteroid_flight` | verification requires a new fleet ID, exact source, exact target, and mission `Добыча газа` |
| Ambiguous side effect | journal + bounded workflow | series stops on first ambiguity; no third candidate and no automatic repeat |
| Process restart / auto-repeat | no V2 asteroid timer/scheduler/arming state exists | every process starts with no asteroid automatic loop because auto-repeat remains explicitly deferred |

## Manual-stop semantics

V2-57 intentionally used a synchronous, manually confirmed bounded series. V2-58 adds an explicit Stop control without weakening side-effect safety.

The Stop contract is deliberately **not** “cancel the current HTTP/SendFleet operation”. Cancellation after the game may already have accepted a request would create an unknowable remote-effect state and could encourage a duplicate resend.

Instead:

1. the currently started candidate is allowed to finish into its journaled `verified`, `ambiguous`, or proven safe failure state;
2. the Qt page pumps UI events only between completed remote attempts;
3. Stop sets an in-memory flag;
4. the workflow checks the flag before allocating the next request ID and before starting the next side effect;
5. when set, the workflow returns typed `STOPPED_MANUAL` and starts no further candidate.

While a series is active, the page disables read/prepare/send controls, source/recycler/safety inputs, and candidate table interaction. Only the Stop control remains available for the bounded series. There is still no timer or background asteroid scheduler.

## Crash / restart behavior

The asteroid journal writes immutable `pending` intent before the remote dispatch boundary. A process termination can therefore leave `pending` rather than inventing a safe retry state.

V2-58 adds an explicit simulated crash-window test using a `BaseException` after the pending commit. After reopening the same V2 database, a new request for the same trajectory is rejected before backend dispatch. This proves the intended restart behavior independently of normal exception classification.

Normal unclassified `Exception` after pending is even more conservative: the coordinator records `ambiguous` and blocks automatic retry.

## Live safety immediately before SendFleet

The real CDP backend does not trust a preparation snapshot for the final mutation. Immediately before the single click it rechecks:

- the same live asteroid trajectory;
- deterministic target prediction at the current send time;
- movement safety margin;
- recycler fleet composition;
- mission `Добыча газа`;
- exact target form values;
- `FleetsCount / MaxFleets` capacity;
- CAPTCHA state.

A mismatch is rejected before SendFleet. The backend contains one SendFleet click site and no retry loop.

## Verification / ambiguity boundary

After an accepted-looking SendFleet response, V2 verifies only a newly observed flight row that has:

- a fleet ID absent from the pre-send set;
- exact source coordinates;
- exact target coordinates;
- mission `Добыча газа`.

If that evidence never appears, the result is `ambiguous` even when the server may have accepted the request. If CAPTCHA appears during the post-send verification window, verification stops and the result still becomes `ambiguous`; CAPTCHA is never clicked or solved.

## Candidate-state parity

V2-owned asteroid evidence is independent of legacy mutable storage and survives restart. There is intentionally no age-only TTL because V2-51 found no accepted legacy contract for one. A proven movement trajectory remains usable until deterministic prediction leaves the supported coordinate range or later live evidence contradicts it.

V2-56 removed the accidental 5000-row projection cap; all persisted valid evidence participates by default, with regression coverage across 5001 observations and restart.

## Explicitly deferred after V2-58

The following are **not** part of the completed asteroid parity gate:

- asteroid auto-repeat / continuous asteroid scheduler;
- automatic system traversal or `refreshGalaxy` navigation;
- unattended browser launch or new-tab creation;
- debris / recycling action execution;
- automatic message deletion;
- CAPTCHA solving/clicking/bypass;
- default Tkinter → Qt launcher cutover.

Asteroid auto-repeat is not partially armed or hidden behind a persisted setting in V2. There is no V2 asteroid scheduler to restore after restart.

## Next batch

After V2-58 is squash-merged and push-CI is green on its exact main SHA:

1. record the exact asteroid-parity squash SHA in the V2 handoff/current-state docs;
2. create a fresh debris/recycling contract plan;
3. start debris/recycling migration with an audit/fixture stage, not a direct side-effect implementation.

Do not reuse legacy `debris_asteroids_feature.py` mutation code as a shortcut. The same typed action → gate → journal → exactly-one-attempt → verification/recovery discipline applies to debris actions.
