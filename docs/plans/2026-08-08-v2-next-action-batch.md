# V2 next action batch — fresh reconnaissance → queue refill → controlled AutoFarm

Date: 2026-08-08

Status: planned after the completed V2-31…V2-40 action batch.

Implementation code baseline before this docs-only handoff: `a3db5b277ecea3ef5358a9cd9b0e3f93eebb8dd9`.

## Goal

Close the remaining gap in the V2 raid loop:

`fresh reconnaissance -> verified report facts -> V2-owned targets/queue -> controlled AutoFarm`

V2 already has a guarded raid dispatch path, V2-owned queue, persistent action journal, reconciliation and a controlled AutoFarm scheduler. What is missing is safe acquisition of fresh spy reports and deterministic refill/rebuild of the V2 queue from those verified reports.

This batch must not migrate asteroids/debris at the same time.

## Non-negotiable safety rules

1. Start every implementation PR from fresh `main` after the previous PR is squash-merged.
2. Never modify `stable/tkinter-v1` or `archive/pre-pyside6-4e01bfda`.
3. Legacy SQLite remains read-only.
4. V2 mutable state remains under `%LOCALAPPDATA%/NemexiaRaidManagerV2/`.
5. CAPTCHA remains fail-closed: stop/report only; never solve, click or bypass it.
6. Do not add automatic browser launch, tab creation or arbitrary navigation unless a later explicit design decision changes the attach-only contract.
7. Do not delete game messages/reports in this batch.
8. Any new side effect must have a typed command, explicit action gate, persistent request identity and conservative ambiguous handling before continuous automation can call it.
9. Never automatically retry an action when the remote side effect may already have happened.
10. UI text must render typed state; UI strings must never drive business logic.
11. Every PR must pass Windows Python 3.10, Windows Python 3.11 and PySide6 offscreen smoke before merge.
12. After every squash merge, verify push-CI on the exact new `main` SHA.

## First step before implementation

Do not assume the old spy/report flow from memory. Inspect the effective legacy runtime first:

- report/message acquisition paths in `browser.py` and related patch modules;
- exact selectors/endpoints used for spy requests and report refresh;
- report identity/timestamp/target facts available after a request;
- current resource eligibility rules used by metal/mineral queue modes and AutoFarm;
- current 25-minute successful-empty-scan cooldown contract;
- current behavior when there are no fresh spy reports at all;
- CAPTCHA detection points;
- any current message deletion behavior, which must not be copied into V2 automatically.

Add fixtures/tests before moving browser-side mutation.

## Proposed logical PR sequence

GitHub PR numbers are intentionally not pre-assigned because this documentation PR itself consumes a PR number. Use the V2 sequence identifiers below.

### V2-41 — spy/report contract audit + fixtures

No game mutation.

- map the effective legacy spy/report workflow and selector/end-point contracts;
- add sanitized HTML/response fixtures where useful;
- define typed report identity, freshness and target facts;
- lock the distinction between `no fresh reports`, `fresh reports but zero eligible targets`, CAPTCHA and live-unavailable;
- document the current eligibility/cooldown semantics that must be preserved.

Acceptance: behavior is described and testable before any spy request is moved.

### V2-42 — attach-only report source + freshness reader

Read-only browser work.

- attach to the already-open supported page/session;
- read report/message rows needed for reconciliation and freshness;
- parse report ID, target, timestamps and available resource facts through typed models;
- expose the data through application services, not directly from Qt;
- no spy request and no deletion.

Acceptance: V2 can distinguish fresh/stale/no-report states without mutating the game.

### V2-43 — typed spy request boundary

Create the mutation contract before exposing it.

- typed `SpyRequestCommand` and result/preparation models;
- validation for source/target and required probe/ship facts;
- explicit reuse of the global action gate or a narrower compatible gate;
- backend interface separated from browser implementation;
- fail closed on invalid state/CAPTCHA.

Acceptance: pure application contract has no Playwright click/send implementation.

### V2-44 — persistent spy action journal + idempotency

Persistence gate before real spy requests.

- V2-owned journal table or a typed extension of the existing action-journal design;
- unique immutable request IDs;
- `pending / verified / ambiguous / failed-safe` style states as appropriate;
- block duplicate source/target requests while a prior side effect is unresolved;
- never write legacy SQLite.

Acceptance: crash/duplicate behavior is safe before request dispatch is enabled.

### V2-45 — one-shot verified fresh spy acquisition

First real spy mutation, still manual/explicit.

- perform exactly one request through the validated/journaled boundary;
- verify success through a new exact report/message identity and matching target/freshness facts;
- CAPTCHA/rejection/unreadable response fails closed;
- accepted-but-unverified becomes ambiguous;
- no automatic retry;
- no report/message deletion.

Acceptance: one manually triggered spy request can be proven or left safely unresolved.

### V2-46 — V2-owned recon/target ingestion

No new side effect beyond the already verified report acquisition.

- normalize fresh report facts into V2-owned data;
- preserve provenance: report ID, report time, target and resource facts used for eligibility;
- reject stale/partial evidence rather than silently treating it as fresh;
- make Recon/Targets surfaces read from the typed application layer;
- keep legacy DB as input/reference only where still needed.

Acceptance: fresh reports have a deterministic V2 representation independent of legacy mutation.

### V2-47 — deterministic queue builder/refill policy

No continuous spy loop yet.

- implement queue generation/refill as a pure policy over verified fresh V2 report facts;
- preserve the currently accepted metal/mineral eligibility semantics unless an explicit owner decision changes them;
- respect enabled/blacklisted state and existing non-retryable `sending/sent/ambiguous` rows;
- prevent duplicate target rows during rebuild/refill;
- expose preview/diff facts so the UI can show what will be added/kept/skipped.

Acceptance: the same verified input produces the same queue result without browser access.

### V2-48 — controlled recon → refill integration

Connect acquisition and queue policy without creating a blind background loop.

- when the farm queue is exhausted, surface a typed need-for-recon state;
- run fresh reconnaissance only through the journaled one-shot boundary;
- ingest only verified fresh reports;
- rebuild/refill only after acquisition is verified;
- preserve the successful-fresh-scan-with-zero-eligible-targets cooldown contract (currently 25 minutes) separately from attack return-buffer logic;
- `no fresh reports at all` remains an error/stop condition, not the 25-minute empty-result state.

Acceptance: one controlled cycle can move from empty queue to fresh verified reports to a safe refill, or stop in a typed reason.

### V2-49 — continuous-cycle hardening and recovery

Only after V2-48 is green.

Test and harden at least:

- application restart while cooldown is active;
- restart with pending/ambiguous spy request;
- CAPTCHA during acquisition;
- live browser unavailable;
- fresh scan with zero eligible targets;
- stale reports only;
- duplicate target reports;
- full fleet capacity;
- farm attacks returning + configured return buffer;
- ambiguous SendFleet or spy side effect;
- manual stop/disarm;
- scheduler must still start disarmed on every new process.

No unsafe automatic retry may be introduced to make these tests pass.

### V2-50 — raid-loop parity gate + documentation

No feature expansion unless a parity defect requires it.

- compare V2 raid-loop outcomes against the accepted legacy contracts;
- run full CI and Qt smoke on final code+docs head;
- update `docs/v2-current-state.md` with exact final squash SHA;
- record remaining gaps explicitly;
- decide the next batch: asteroid action migration first, then debris/recycling, unless a discovered dependency requires a different order.

Acceptance: the V2 raid loop is self-contained enough that fresh recon and queue refill no longer depend on legacy mutation code.

## Explicitly deferred until after V2-50

- asteroid execution / auto-repeat;
- debris/recycling execution;
- message deletion;
- automatic CAPTCHA interaction;
- changing the default launcher from Tkinter to Qt;
- deleting legacy Tkinter/patch modules;
- merging V2 and legacy runtime data roots;
- unattended browser launch/navigation.

## Review discipline

For every PR:

1. inspect the exact current `main` SHA;
2. create a fresh feature branch;
3. read the effective call sites before editing;
4. add/adjust tests with the behavior change;
5. run CI;
6. inspect review findings and fix substantive P1/P2 issues;
7. squash merge only when green;
8. verify push-CI on the resulting `main` SHA;
9. only then start the next PR.

If an old source-contract test fails because architecture intentionally changed, narrow the test to the actual invariant; do not weaken the safety invariant itself.
