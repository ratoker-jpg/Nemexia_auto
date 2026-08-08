# V2 asteroid action migration — V2-51→V2-58

Date: 2026-08-08

Baseline for this batch: V2-50 squash `4e147f7f51cae9f063fabf7ad069e0b0be48a4bc` / PR #82, after its exact-SHA docs handoff.

Source contracts:

- `docs/v2-current-state.md`;
- `docs/audits/2026-08-08-v2-raid-loop-parity-gate.md`;
- `docs/plans/2026-08-06-debris-asteroid-workflow.md`;
- effective legacy asteroid implementation in `browser.py`, `asteroids.py`, `debris_asteroids_feature.py` and installed patch modules/tests.

## Goal

Migrate asteroid **actions first** into V2 without importing debris/recycling execution yet and without weakening the action-safety model established for raid and spy mutations.

Every remote asteroid side effect must keep this order:

```text
typed command
→ validation
→ explicit actions_enabled gate
→ read-only preparation
→ persistent immutable request identity
→ idempotency
→ exactly one remote mutation attempt
→ verified / ambiguous result
→ restart recovery
```

No continuous asteroid scheduler may use a side effect until that chain exists and its recovery behavior is tested.

## Safety constraints

- V2 remains attach-only: no browser launch, new tabs or unattended navigation.
- CAPTCHA is detect + stop only; never solve/click/bypass.
- Legacy SQLite remains read-only.
- No automatic retry after an ambiguous remote effect.
- No automatic message deletion.
- Do not migrate debris/recycling execution in this batch.
- Do not change the default Tkinter launcher.
- Do not touch `stable/tkinter-v1` or `archive/pre-pyside6-4e01bfda`.
- Existing asteroid movement/time formulas may be reused only after their effective legacy semantics are pinned by fixtures/tests; do not copy UI text-driven logic.

## V2-51 — asteroid contract audit + fixtures

Research/contract PR only. No game mutation.

- identify the effective legacy asteroid workflow and installed patch call sites;
- pin exact DOM selectors/endpoints/JS functions used for galaxy scan, `squareInfo`, fleet preparation and send;
- pin source planet, asteroid identity, current/next movement timestamps and coordinate semantics;
- pin future-position/stabilization and movement-margin rules from `asteroids.py`;
- pin recycler availability, live fleet capacity and mission verification facts;
- distinguish no asteroid / stale observation / moved asteroid / capacity / CAPTCHA / browser unavailable / ambiguous send;
- add sanitized fixtures and contract tests before moving browser mutation.

Acceptance: V2 has a documented, testable asteroid contract with no new side effect.

## V2-52 — attach-only asteroid observation reader

Read-only V2 source.

- read only already-open required game surfaces;
- expose typed asteroid observations and freshness/movement facts;
- fail unavailable rather than navigating;
- no send, no scan mutation, no scheduler.

Acceptance: V2 can prove an asteroid observation without changing the game.

## V2-53 — typed asteroid dispatch boundary

Mutation contract before browser implementation.

- typed command/preparation/result models;
- validate source, asteroid observation, recycler count and movement facts;
- reuse the explicit global `actions_enabled` gate;
- backend interface separate from CDP implementation;
- fail closed on invalid/stale/CAPTCHA state.

Acceptance: pure application boundary has no remote send implementation.

## V2-54 — persistent asteroid journal + idempotency

Persistence gate.

- V2-owned journal table/state;
- immutable request IDs;
- unresolved request blocking for the exact prepared asteroid dispatch identity;
- pending written before the side effect;
- verified / ambiguous / failed-safe states and restart-safe reads;
- never write legacy SQLite.

Acceptance: duplicate/crash behavior is safe before browser send is enabled.

## V2-55 — exactly-one verified asteroid dispatch

First real asteroid mutation, manual/explicit only.

- perform exactly one remote send through the validated/journaled boundary;
- re-check the exact observation/movement facts immediately before send;
- calculate the target deterministically from the pinned movement contract;
- verify by a new exact fleet ID + expected asteroid target + mission `Добыча газа`;
- CAPTCHA/rejection/unreadable pre-send fails closed;
- accepted-but-unverified is ambiguous;
- never automatically retry an ambiguous send.

Acceptance: one manually requested asteroid dispatch is either verified or safely unresolved.

## V2-56 — V2-owned asteroid candidate state

No new side effect.

- normalize proven observations into V2-owned state;
- preserve provenance and movement timestamps;
- deterministic candidate ordering/filtering;
- reject stale/partial observations rather than silently promoting them;
- expose typed preview/diff facts for UI.

Acceptance: candidate state is independent of legacy mutable storage.

## V2-57 — controlled Qt asteroid workflow

Connect read/prepare/manual send through typed state.

- add/complete the V2 Asteroids surface;
- scan/read/preview remain explicit and attach-only;
- selected dispatches use only V2-55 journaled boundary;
- series stops at first CAPTCHA, ambiguity or error;
- UI strings never drive execution decisions.

Acceptance: the operator can inspect candidates and explicitly send a bounded selected set with safe stop behavior.

## V2-58 — asteroid recovery/parity gate

Only after V2-57 is green.

Test and document at least:

- restart with pending/ambiguous asteroid request;
- moved/stale asteroid before send;
- insufficient recyclers;
- full fleet capacity;
- CAPTCHA before/after potential acceptance;
- duplicate candidate/dispatch identity;
- manual stop;
- exact new-flight verification;
- no automatic retry after ambiguity;
- no automatic scheduler starts after restart.

If auto-repeat is migrated here, it must start disarmed on every process and may only call the already-proven journaled boundary. Otherwise leave auto-repeat explicitly deferred.

Acceptance: asteroid action parity is documented and safe enough to begin the **separate** debris/recycling migration batch.

## Per-PR discipline

For every stage:

1. confirm exact current `main` SHA;
2. create a fresh branch;
3. inspect current call sites before editing;
4. implement + tests;
5. run the full Windows/PySide6 CI gate;
6. inspect review and fix substantive P1/P2 findings;
7. squash merge only when green;
8. verify push-CI on the exact squash SHA;
9. only then start the next stage.
