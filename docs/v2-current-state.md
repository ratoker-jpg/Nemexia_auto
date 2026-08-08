# Nemexia Raid Manager V2 — current state

Current completed **action-migration** baseline:

- `1077125a59a96274017ad09c9814431bdaeb614e`
- PR #101 / V2-66 — debris/recycling parity gate
- exact push-CI: run #206 — green on Windows Python 3.10, Windows Python 3.11 and PySide6 offscreen smoke

V2-59→V2-66 debris/recycling migration is fully merged. The exact final action squash is pinned above. Automatic browser navigation and the legacy 3×40 debris traversal remain intentionally deferred.

## Completed V2 action batches

### Raid action migration — V2-31→V2-40

PR #62–#71 established:

- typed raid commands;
- attach-only raid preparation;
- explicit `actions_enabled` gate;
- exactly-one SendFleet attempt;
- persistent raid journal/idempotency;
- V2-owned raid queue;
- manual Plan dispatch;
- reconciliation of pending/ambiguous raids;
- typed AutoFarm state machine;
- explicitly armed in-session scheduler.

Final batch baseline: `a3db5b277ecea3ef5358a9cd9b0e3f93eebb8dd9`.

### Fresh reconnaissance / refill — V2-41→V2-50

PR #73–#82 established:

- attach-only rendered spy-report reader;
- exact `processSpy(fleet_id)`, never bulk `processSpy(0)`;
- persistent spy journal and exactly-one verified report acquisition;
- V2-owned recon targets/reports;
- deterministic metal/mineral/AutoFarm refill;
- 25-minute successful-empty-scan cooldown;
- fail-closed recovery with no retry after ambiguity.

Final batch squash: `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` / PR #82.

Detailed parity record: [`audits/2026-08-08-v2-raid-loop-parity-gate.md`](audits/2026-08-08-v2-raid-loop-parity-gate.md).

### Asteroid action migration — V2-51→V2-58

PR #84–#92 established:

- asteroid movement/dispatch contract audit and sanitized fixtures;
- attach-only current-system asteroid reader;
- typed asteroid dispatch;
- persistent `asteroid_actions` unresolved-trajectory idempotency;
- exactly-one verified recycler SendFleet with fresh live re-check;
- immutable `asteroid_observations` and deterministic candidate projection;
- real Qt Asteroids page with bounded multi-selection, read-only preparation, explicit confirmation and manual Stop;
- restart recovery, no retry and no scheduler.

Final batch squash: `b5d57bf620a1567b63f15a29ac8ff382692fd943` / PR #92.

Detailed parity record: [`audits/2026-08-08-v2-asteroid-parity-gate.md`](audits/2026-08-08-v2-asteroid-parity-gate.md).

### Debris / recycling migration — V2-59→V2-66

PR #94–#101 established:

- V2-59 / PR #94 / `7041ebcee0a96474de9800cf6b454c6e6c9fec6e` — exact `squareInfo` debris contract, sanitized fixtures, legacy scan completion/cancel semantics and proof that debris must reuse asteroid mutation;
- V2-60 / PR #95 / `00784ede604a3d4674596b4b8fbe3aa1b620f74e` — attach-only current-system debris reader with distinct `no_debris`, CAPTCHA, unavailable and partial/unreadable states;
- V2-61 / PR #96 / `84d22044d34c0122506217df6f23ead2b868fa03` — append-only V2-owned debris evidence, exact duplicate idempotency and deterministic current-coordinate candidates;
- V2-62 / PR #97 / `c8aa2aa9582a107689112b28a48f2173bc900450` — typed debris → existing asteroid command mapping and proof that debris labels/request IDs cannot bypass the same unresolved trajectory guard;
- V2-63 / PR #98 / `27d0b299cfae9a0ef5f0f4953a80baa8efa9b916` — bounded prepare → single-use explicit confirmation → dispatch workflow, stop-on-first failure/ambiguity/CAPTCHA/manual Stop, no retry/scheduler;
- V2-64 / PR #99 / `1e6726d35f8da6e7dd3c73313028bf890c8080e6` — real Qt Debris page; review corrected the legacy default to debris-specific `debris_recyclers`;
- V2-65 / PR #100 / `fb8628b0c38840936f95fee9d84703969d6e5c13` — restart/recovery/discovery/lifecycle hardening, including stale confirmation disarm on input/selection/page/window lifecycle;
- V2-66 / PR #101 / `1077125a59a96274017ad09c9814431bdaeb614e` — final debris parity/recovery gate.

Detailed parity record: [`audits/2026-08-08-v2-debris-parity-gate.md`](audits/2026-08-08-v2-debris-parity-gate.md).

## Safety baseline

Rollback refs remain untouched:

- `stable/tkinter-v1`
- `archive/pre-pyside6-4e01bfda`
- original stable Tkinter SHA `4e01bfda752c6383e48c0f6eb8be64d68676da67`

Default launcher remains:

```text
run_app.bat -> app_entry.py
```

PySide6 remains a separate opt-in entrypoint:

```text
app_qt.py
```

No Tkinter → Qt cutover has occurred.

## Storage boundary

Legacy SQLite remains strictly read-only:

- URI `mode=ro`;
- `PRAGMA query_only=ON`;
- no V2 mutation of legacy targets/history/queue/recon/settings.

V2-owned runtime storage remains under `%LOCALAPPDATA%/NemexiaRaidManagerV2/`.

Current core V2 SQLite schema version: **8**.

V2-owned state includes:

- allow-listed typed settings;
- `raid_actions`;
- `raid_queue`;
- `spy_actions`;
- `recon_targets`;
- immutable `recon_reports`;
- `asteroid_actions`;
- immutable `asteroid_observations`;
- additive immutable `debris_observations` evidence.

`debris_observations` is feature-local additive storage and does not modify legacy SQLite. A `no_debris` result from one currently opened system never deletes evidence learned from other systems.

## Browser boundary

V2 remains attach-only. It uses an existing Chromium/Yandex CDP session and does not launch the browser, create tabs or navigate the account automatically.

Current live prerequisites depend on the action:

- already-open `fleets.php` for fleet/capacity/raid/spy/asteroid/debris-send facts;
- already-rendered System messages on `options.php` for spy-report verification;
- already-open `galaxy.php` for explicit current-system asteroid/debris observation.

V2 does **not** automatically switch galaxy systems or traverse 3×40 systems.

CAPTCHA remains strict detect → STOP. V2 never solves, clicks or bypasses CAPTCHA.

## Raid mutation boundary

Raid actions require `actions_enabled=true` and preserve typed validation, read-only preparation, persistent request identity, exactly one SendFleet attempt, exact new-flight verification and no automatic retry after ambiguity.

## Spy / fresh-report mutation boundary

V2 does not use `processSpy(0)`. Supported mutation remains exactly one already-existing espionage row via `processSpy(fleet_id)`, with persistent request identity, exact report verification and fail-closed ambiguity/CAPTCHA handling.

## Recon / queue contracts

Nemexia report wall-clock is interpreted as server UTC+04 and normalized to UTC. Default freshness window remains 24 hours. Missing timestamps are never replaced by current time.

Fresh reports + zero eligible targets remains a successful empty scan with a persisted 25-minute cooldown. Missing/stale/partial/CAPTCHA/live-unavailable evidence is a stop state, not that cooldown.

## AutoFarm V2

Continuous mode still starts disarmed on process launch and requires explicit manual Start. Scheduler arm and exact Spy fleet ID are session-only. Pending/ambiguous side effects, CAPTCHA, stale/no fresh evidence, live failure or wave failure disarm the cycle.

## Shared asteroid / debris mutation boundary

There is exactly **one authoritative recycler SendFleet boundary** for generic asteroid and debris execution.

Controlled dispatch follows:

1. immutable proven `AsteroidObservationFact` — directly or wrapped by a proven `DebrisObservationFact`/candidate;
2. typed validation + `actions_enabled`;
3. read-only preparation;
4. deterministic current-coordinate prediction from movement provenance;
5. recycler availability / live fleet capacity / movement-margin checks;
6. persistent `asteroid_actions` unresolved trajectory identity before SendFleet;
7. fresh live trajectory + target + recycler + capacity + CAPTCHA re-check immediately before mutation;
8. exactly one SendFleet attempt;
9. exact new fleet ID + source + target + mission `Добыча газа` verification;
10. `verified` / `ambiguous` / `failed_safe` journal result;
11. no automatic retry after ambiguity.

Debris does **not** have a second browser SendFleet implementation and does **not** have a `debris_actions` journal. A different UI label, request ID or recycler count cannot create a retry namespace for the same unresolved trajectory.

Crash/restart is conservative: unresolved `pending` or `ambiguous` `asteroid_actions` identity blocks another attempt after restart.

## V2-owned debris discovery/evidence

The accepted debris marker is the `squareInfo` evidence:

```text
Этот астероид содержит обломки
```

V2 normalizes presentation markup but requires the same complete asteroid movement provenance used by the asteroid reader. A marker with partial/unreadable movement facts is `partial_evidence`, not `no_debris`.

A fully readable currently opened system with no marker is `no_debris` **for that system only**.

Evidence is append-only across manually opened systems. V2 never claims that reading one or several manually opened systems is a completed legacy 120-system scan.

## Controlled Qt asteroid and debris workflows

Both real pages support bounded typed multi-selection, read-only preparation, explicit confirmed journaled dispatch and manual Stop between side effects.

The Debris page additionally supports explicit `Прочитать открытую систему` current-system evidence ingestion. It exposes CAPTCHA/unavailable/partial/no-debris states rather than hiding them.

Manual Stop never cancels an already-started remote attempt. It prevents the next request only after the current attempt settles. Debris unconfirmed preparation is also disarmed when selection/config changes, the page is hidden or the context/window closes.

There is no asteroid or debris auto-repeat scheduler.

## Qt surfaces

Real PySide6 application surfaces include:

- Overview;
- Plan;
- Active;
- AutoFarm;
- Asteroids;
- Debris;
- Recon;
- Targets;
- History;
- Settings;
- Diagnostics.

## Explicitly deferred

Still not enabled in V2:

- automatic message deletion;
- automatic CAPTCHA interaction;
- unattended browser launch/navigation;
- automatic galaxy/system traversal, including legacy 3×40 debris scanning;
- creation of a new espionage route when no exact processable spy fleet row exists;
- asteroid auto-repeat / continuous asteroid scheduler;
- debris auto-repeat / continuous debris scheduler;
- default launcher cutover to Qt;
- deletion of legacy Tkinter/patch modules.

## Next contract batch

The next prepared batch is [`plans/2026-08-08-v2-browser-navigation-contract-batch.md`](plans/2026-08-08-v2-browser-navigation-contract-batch.md).

Its purpose is **not** to turn on automatic 3×40 traversal. It first audits browser/tab/navigation ownership because the old Rest Mode concept and the legacy debris full scan both assume navigation that is currently forbidden by the attach-only baseline.

The next batch must start research-only and may introduce an explicit single-step navigation boundary only if the audit proves safe semantics. Automatic loops/full traversal remain deferred beyond that gate.

Do not implement the old Rest Mode plan literally until this navigation/read ownership contract is proven.

## Verification gate

Every implementation/docs gate remains:

- Windows Python 3.10: compileall + pytest + legacy self-test;
- Windows Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

After every squash merge, push-CI must be verified on the exact new `main` SHA before the next branch starts.
