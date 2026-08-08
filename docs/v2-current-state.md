# Nemexia Raid Manager V2 — current state

Current completed raid-loop parity baseline:

- `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc`
- PR #82 / V2-50 — raid-loop parity gate + documentation

The V2-41→V2-50 fresh-recon batch is fully merged and its exact squash SHA is pinned above. The next implementation batch is asteroid action migration V2-51→V2-58 from `docs/plans/2026-08-08-v2-asteroid-action-batch.md`.

## Completed V2 batches

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
- controlled exact verified recon → ingestion → queue refill;
- persisted 25-minute successful-empty-scan cooldown separate from raid return-buffer;
- continuous in-session recovery from `need_recon` using a user-supplied exact Spy fleet ID;
- global safety blocking on pending/ambiguous raid **or spy** side effects;
- final raid-loop parity/safety gate and exact remaining-gap record.

Final batch squash: `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` / PR #82.

Detailed parity record: [`audits/2026-08-08-v2-raid-loop-parity-gate.md`](audits/2026-08-08-v2-raid-loop-parity-gate.md).

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

Current V2 SQLite schema version: **6**.

V2-owned tables/state now include:

- allow-listed typed settings;
- `raid_actions`;
- `raid_queue`;
- `spy_actions`;
- `recon_targets`;
- immutable `recon_reports`.

Legacy targets/queue may seed missing V2-owned state, but later legacy reads do not overwrite mutable V2 queue/recon state.

## Browser boundary

V2 is attach-only. It uses an existing Chromium/Yandex CDP session and does not launch the browser, create tabs, or navigate the account automatically.

Current live prerequisites:

- an already-open `fleets.php` page for fleet/capacity/raid/spy fleet facts;
- an already-rendered System messages area on `options.php` for spy-report verification.

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

Queue rows become non-retryable before the remote side effect, closing the crash/restart duplicate-send gap.

Pending/ambiguous raids may be reconciled only from live fleet evidence; ambiguous evidence never creates an automatic resend window.

## Spy / fresh-report mutation boundary

V2 does **not** use bulk `processSpy(0)`.

The supported mutation is one exact already-existing espionage row:

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

V2 does not invent a target route and does not yet create a brand-new espionage flight when no processable spy row exists.

## Recon / freshness contracts

Nemexia report wall-clock is interpreted as server UTC+04 and normalized to UTC.

Default freshness window: **24 hours**.

Missing timestamp is never replaced by current time.

V2-owned recon preserves provenance:

- report ID;
- target;
- report timestamp;
- energy;
- metal;
- minerals;
- gas;
- source/ingestion time.

Stale or partial evidence is rejected rather than silently promoted to fresh data.

## Queue policy

Policies remain intentionally distinct.

### Manual metal

```text
metal >= 480,000
```

after enabled/not-blacklisted/not-active/fresh-report filters.

### Manual minerals

A reported mineral value is enough; no 500k threshold.

### AutoFarm

```text
minerals >= 500,000
```

Ranking remains minerals desc → metal desc → coordinate.

Refill is deterministic over V2-owned facts and preserves protected/non-retryable queue rows.

## Recon-cycle outcomes

The following remain separate typed outcomes:

- fresh reports + eligible targets → safe refill;
- fresh reports + zero eligible targets → successful empty scan + **25-minute** cooldown;
- no reports / stale-only → stop, not cooldown;
- CAPTCHA → stop;
- live/browser unavailable → stop;
- exact-report identity mismatch → stop;
- ambiguous spy side effect → stop and unresolved journal.

The 25-minute no-target cooldown is persisted in V2 settings and is separate from attack return-buffer state. Restart during the cooldown does not permit a new spy attempt.

## AutoFarm V2

Current typed states:

- `actions_disabled`;
- `live_not_checked`;
- `live_unavailable`;
- `blocked_unresolved`;
- `waiting_return`;
- `waiting_capacity`;
- `need_recon`;
- `ready`.

A wave is capped by live free fleet slots, eligible V2 queue size, and user max-target limit. It stops at the first error or ambiguity.

Continuous mode:

- starts disarmed on every new process;
- requires explicit manual Start confirmation;
- runs live checks every 30 seconds;
- waits for farm-blocking attacks and configured return buffer;
- blocks globally on unresolved raid or spy journal;
- when queue is exhausted, may recover only through a user-supplied exact Spy fleet ID for that **current session**;
- the scheduler arm and Spy fleet ID are never persisted;
- successful empty scans wait through the persisted 25-minute cooldown without a new spy attempt;
- ambiguity, CAPTCHA, stale/no fresh evidence, live failure or wave failure disarms the cycle.

## Qt surfaces

Real PySide6 application surfaces include:

- Overview;
- Plan;
- Active;
- AutoFarm;
- Recon;
- Targets;
- History;
- Settings;
- Diagnostics.

Asteroids and Debris are not yet migrated as V2 action surfaces.

## Explicitly deferred

Still not enabled in V2:

- automatic message deletion;
- automatic CAPTCHA interaction;
- unattended browser launch/navigation;
- creation of a new espionage route when no exact processable spy fleet row exists;
- asteroid execution / auto-repeat;
- debris/recycling execution;
- default launcher cutover to Qt;
- deletion of legacy Tkinter/patch modules.

## Current implementation order

The next batch is [`plans/2026-08-08-v2-asteroid-action-batch.md`](plans/2026-08-08-v2-asteroid-action-batch.md):

1. V2-51 contract audit + sanitized fixtures;
2. attach-only observation read boundary;
3. typed asteroid dispatch boundary;
4. persistent asteroid journal/idempotency;
5. exactly-one-attempt verified asteroid send;
6. V2-owned candidate state;
7. controlled Qt asteroid workflow;
8. recovery/parity gate.

Only after asteroid parity may a separate debris/recycling action batch start.

Do not combine asteroid and debris migration into one large PR.

## Verification gate

Every implementation/docs gate remains:

- Windows Python 3.10: compileall + pytest + legacy self-test;
- Windows Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

After every squash merge, push-CI must be verified on the exact new `main` SHA before the next branch starts.
