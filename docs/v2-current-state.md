# Nemexia Raid Manager V2 — current state

Current completed action-migration baseline:

- `b5d57bf620a1567b63f15a29ac8ff382692fd943`
- PR #92 / V2-58 — asteroid recovery/parity gate

The V2-51→V2-58 asteroid batch is fully merged and its exact squash SHA is pinned above. The next implementation batch is debris/recycling migration V2-59→V2-66 from `docs/plans/2026-08-08-v2-debris-action-batch.md`.

## Completed V2 action batches

### Raid action migration — V2-31→V2-40

PR #62–#71 established:

- typed raid commands;
- attach-only raid preparation;
- explicit `actions_enabled` gate;
- exactly-one-attempt SendFleet;
- persistent raid journal/idempotency;
- V2-owned raid queue;
- manual Plan dispatch;
- live reconciliation of pending/ambiguous raids;
- typed AutoFarm state machine;
- explicitly armed in-session scheduler.

Code baseline after V2-40: `a3db5b277ecea3ef5358a9cd9b0e3f93eebb8dd9`.

### Fresh reconnaissance / refill — V2-41→V2-50

PR #73–#82 established:

- effective legacy spy/report contract audit and sanitized fixtures;
- attach-only rendered spy-report reader with typed fresh/stale/no-report/CAPTCHA/unavailable states;
- exact-fleet typed `processSpy(fleet_id)` boundary;
- persistent V2 spy journal and idempotency;
- exactly-one-attempt verified fresh report acquisition;
- V2-owned recon targets and immutable report snapshots;
- deterministic manual-metal/manual-mineral/AutoFarm queue policy;
- controlled verified recon → ingestion → queue refill;
- persisted 25-minute successful-empty-scan cooldown separate from raid return-buffer;
- continuous in-session recovery from `need_recon` using a user-supplied exact Spy fleet ID;
- global safety blocking on pending/ambiguous raid or spy side effects;
- final raid-loop parity/safety gate.

Final batch squash: `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` / PR #82.

Detailed parity record: [`audits/2026-08-08-v2-raid-loop-parity-gate.md`](audits/2026-08-08-v2-raid-loop-parity-gate.md).

### Asteroid action migration — V2-51→V2-58

PR #84–#92 established:

- effective asteroid movement/dispatch contract audit + sanitized fixtures;
- attach-only current-system asteroid observation reader;
- typed asteroid dispatch preparation/result boundary;
- V2-owned persistent `asteroid_actions` journal and unresolved-trajectory idempotency;
- exactly-one-attempt verified recycler SendFleet with fresh live re-check immediately before mutation;
- V2-owned immutable `asteroid_observations` and deterministic current-coordinate candidate projection;
- real Qt Asteroids page with explicit read, typed multi-selection, read-only preparation and confirmed bounded dispatch;
- stop-on-first CAPTCHA/ambiguity/error semantics;
- V2-58 manual Stop that blocks the next candidate without cancelling an already-started remote attempt;
- restart recovery proving durable `pending`/`ambiguous` asteroid actions block duplicate side effects;
- final asteroid parity gate covering movement, capacity, recyclers, exact new-flight verification and no-retry/no-scheduler boundaries.

Final asteroid batch squash: `b5d57bf620a1567b63f15a29ac8ff382692fd943` / PR #92.

Detailed parity record: [`audits/2026-08-08-v2-asteroid-parity-gate.md`](audits/2026-08-08-v2-asteroid-parity-gate.md).

## Safety baseline

Rollback refs remain untouched:

- `stable/tkinter-v1`
- `archive/pre-pyside6-4e01bfda`
- original stable Tkinter SHA `4e01bfda752c6383e48c0f6eb8be64d68676da67`

Default launcher is still:

```text
run_app.bat -> app_entry.py
```

PySide6 remains a separate opt-in entrypoint:

```text
app_qt.py
```

No final Tkinter → Qt cutover has occurred.

## Storage boundary

Legacy SQLite remains read-only:

- URI `mode=ro`;
- `PRAGMA query_only=ON`;
- no V2 mutation of legacy targets/history/queue/recon/settings.

V2-owned runtime storage remains under `%LOCALAPPDATA%/NemexiaRaidManagerV2/`.

Current V2 SQLite schema version: **8**.

V2-owned tables/state include:

- allow-listed typed settings;
- `raid_actions`;
- `raid_queue`;
- `spy_actions`;
- `recon_targets`;
- immutable `recon_reports`;
- `asteroid_actions`;
- immutable `asteroid_observations`.

Legacy targets/queue may seed missing V2-owned state, but later legacy reads do not overwrite mutable V2 queue/recon/asteroid state.

## Browser boundary

V2 is attach-only. It uses an existing Chromium/Yandex CDP session and does not launch the browser, create tabs, or navigate the account automatically.

Current live prerequisites depend on the action:

- already-open `fleets.php` for fleet/capacity/raid/spy/asteroid-send facts;
- already-rendered System messages on `options.php` for spy-report verification;
- already-open `galaxy.php` for explicit current-system asteroid observation.

V2 does **not** automatically switch galaxy systems or traverse 3×40 systems.

CAPTCHA remains strict stop/fail-closed. V2 never solves, clicks, or bypasses CAPTCHA.

## Raid mutation boundary

Raid actions are disabled by default and require `actions_enabled=true`.

Every raid mutation follows:

1. typed validation;
2. read-only preparation;
3. exact source/target/ship facts;
4. persistent immutable `request_id` before SendFleet;
5. exactly one SendFleet attempt;
6. exact new fleet ID + target + mission `Атака` verification;
7. verified or ambiguous result;
8. no automatic retry after ambiguity.

Pending/ambiguous raids may be reconciled only from live fleet evidence; ambiguity never creates an automatic resend window.

## Spy / fresh-report mutation boundary

V2 does **not** use bulk `processSpy(0)`.

Supported mutation is one exact already-existing espionage row:

```text
processSpy(fleet_id)
```

The path is:

1. caller supplies exact `fleet_id`;
2. V2 proves the exact DOM row and derives source/target from it;
3. rendered report source must already be available;
4. persistent immutable spy request ID is written before mutation;
5. exactly one `processSpy(fleet_id)` attempt;
6. success requires a new report ID + exact target + fresh timestamp;
7. ambiguous/unreadable/CAPTCHA results stop without automatic retry.

V2 does not invent a target route and does not create a brand-new espionage flight when no processable spy row exists.

## Recon / queue contracts

Nemexia report wall-clock is interpreted as server UTC+04 and normalized to UTC.

Default freshness window: **24 hours**. Missing timestamp is never replaced by current time.

V2-owned recon preserves report ID, target, timestamp, energy, metal, minerals, gas and source/ingestion provenance. Stale or partial evidence is rejected.

Queue policies remain distinct:

- manual metal: `metal >= 480,000` after target/freshness filters;
- manual minerals: any reported mineral value;
- AutoFarm: `minerals >= 500,000`, ranking minerals desc → metal desc → coordinate.

Fresh reports + zero eligible targets is a successful empty scan with a persisted **25-minute** cooldown. No reports/stale-only/CAPTCHA/live failure is a stop state, not that cooldown.

## AutoFarm V2

Continuous mode:

- starts disarmed on every new process;
- requires explicit manual Start;
- checks live state every 30 seconds;
- waits for farm-blocking attacks and configured return buffer;
- blocks globally on unresolved raid or spy journal;
- may recover an empty queue only through a user-supplied exact Spy fleet ID for the current session;
- scheduler arm and Spy fleet ID are not persisted;
- ambiguity, CAPTCHA, stale/no fresh evidence, live failure or wave failure disarms the cycle.

## Asteroid mutation boundary

Asteroid/recycler execution is migrated, but automatic asteroid cycling is not.

A controlled asteroid dispatch follows:

1. exact V2-owned `AsteroidObservationFact` / candidate;
2. typed validation and `actions_enabled` gate;
3. read-only preparation;
4. deterministic current-coordinate prediction from movement provenance;
5. recycler availability / live fleet capacity / movement safety checks;
6. persistent immutable `asteroid_actions` request identity before SendFleet;
7. fresh live trajectory + target + recycler + capacity + CAPTCHA re-check immediately before mutation;
8. exactly one SendFleet attempt;
9. exact new fleet ID + exact source + exact target + mission `Добыча газа` verification;
10. verified / ambiguous / failed-safe journal state;
11. no automatic retry after ambiguity.

Crash/restart behavior is conservative: unresolved `pending` or `ambiguous` trajectory identity blocks a new attempt.

### V2-owned asteroid candidate state

`asteroid_observations` stores immutable movement evidence with provenance:

- origin galaxy/system/position;
- last and next movement time;
- period;
- observation time;
- evidence source.

Candidate projection is deterministic. Exact duplicate evidence is idempotent; multiple proven observations may remain for provenance while the current candidate view deduplicates by predicted current coordinate.

There is intentionally **no age-only TTL** for a proven movement trajectory because the accepted legacy contract did not establish one. Evidence remains usable until deterministic prediction leaves the supported coordinate range or newer live evidence contradicts it.

The accidental 5000-row projection cap found during V2-56 review was removed; valid persisted evidence is not silently truncated.

### Controlled Qt asteroid workflow

The real Asteroids page supports:

- explicit read of the already-open current `galaxy.php` system;
- V2-owned evidence ingestion/candidate preview;
- typed multi-selection bounded to 200 candidates;
- read-only preparation before confirmation;
- explicit confirmed journaled dispatch;
- stop at first CAPTCHA, ambiguity or error;
- manual Stop between side effects.

Manual Stop never cancels an already-started remote attempt. It prevents allocation/start of the next request only after the current attempt has settled into its journaled result. Hiding the Asteroids page or closing its parent window also requests Stop before the next candidate.

There is no V2 asteroid scheduler or persisted asteroid auto-repeat arm.

## Qt surfaces

Real PySide6 application surfaces include:

- Overview;
- Plan;
- Active;
- AutoFarm;
- Asteroids;
- Recon;
- Targets;
- History;
- Settings;
- Diagnostics.

Debris remains a placeholder and is the next migration target.

## Explicitly deferred

Still not enabled in V2:

- automatic message deletion;
- automatic CAPTCHA interaction;
- unattended browser launch/navigation;
- automatic galaxy/system traversal;
- creation of a new espionage route when no exact processable spy fleet row exists;
- asteroid auto-repeat / continuous asteroid scheduler;
- debris/recycling V2 evidence + controlled execution surface;
- default launcher cutover to Qt;
- deletion of legacy Tkinter/patch modules.

## Current implementation order

The next batch is [`plans/2026-08-08-v2-debris-action-batch.md`](plans/2026-08-08-v2-debris-action-batch.md):

1. V2-59 debris contract audit + sanitized fixtures;
2. V2-60 attach-only current-system debris reader;
3. V2-61 V2-owned debris evidence/candidate state;
4. V2-62 prove/reuse the existing asteroid mutation boundary or stop if a real side-effect difference exists;
5. V2-63 controlled bounded debris dispatch workflow;
6. V2-64 real Qt Debris surface;
7. V2-65 recovery/discovery hardening;
8. V2-66 debris parity gate + handoff.

The legacy automatic 3×40 debris scan is **not** part of this batch because automatic browser navigation remains deferred. Current-system reads may accumulate evidence but must never pretend to be a completed full scan.

Do not create a second SendFleet/journal implementation if V2-59/V2-62 prove that debris dispatch is the same migrated asteroid `Добыча газа` side effect.

## Verification gate

Every implementation/docs gate remains:

- Windows Python 3.10: compileall + pytest + legacy self-test;
- Windows Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

After every squash merge, push-CI must be verified on the exact new `main` SHA before the next branch starts.
