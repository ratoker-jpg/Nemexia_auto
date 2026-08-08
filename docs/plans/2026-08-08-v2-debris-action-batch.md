# Nemexia Raid Manager V2 — debris/recycling action batch

Date: 2026-08-08

Starting baseline:

- `b5d57bf620a1567b63f15a29ac8ff382692fd943`
- PR #92 / V2-58 — asteroid recovery/parity gate

The V2-51→V2-58 asteroid batch is complete. This plan starts the next separate migration batch for asteroids that contain debris and recycler dispatch.

## Non-negotiable boundaries

This batch must preserve the existing V2 safety baseline:

- legacy SQLite remains strictly read-only;
- `run_app.bat -> app_entry.py` remains the default launcher;
- rollback refs remain untouched;
- V2 remains attach-only;
- no unattended browser launch, new tabs, `goto`, `refreshGalaxy`, or automatic 3×40 system traversal;
- CAPTCHA is detect + stop only;
- no message deletion;
- no automatic retry after a potentially accepted remote side effect;
- no debris auto-repeat/scheduler;
- UI text never drives business logic.

The legacy debris workflow traverses galaxies 1–3 and systems 40→1 automatically. That traversal is **not** migrated in this batch because automatic browser navigation is still explicitly deferred. V2 discovery must operate on already-open live pages until a separate navigation contract is approved.

## Important reuse question

Legacy debris dispatch targets an asteroid and uses the recycler mission already used by the migrated V2 asteroid action path. Therefore this batch must **not** assume that debris requires a second SendFleet implementation or a second action journal.

V2-59 must first prove whether a debris candidate can safely reuse the existing V2 asteroid mutation boundary:

```text
AsteroidDispatchCommand
→ validation / actions_enabled
→ persistent asteroid_actions request identity
→ fresh live trajectory + recycler + capacity re-check
→ exactly one SendFleet attempt
→ exact new flight ID + source + target + mission Добыча газа verification
→ verified / ambiguous / failed-safe
```

If the audit proves a meaningful side-effect difference, stop and document it before adding any new mutation path. Do not create a parallel journal/backend merely for naming symmetry.

## V2-59 — debris contract audit + sanitized fixtures

Research/contract PR only.

- inspect effective legacy `debris_asteroids_feature.py` call sites and any patches that alter them;
- prove the exact `squareInfo` evidence used to recognize `Этот астероид содержит обломки`;
- record exact movement/provenance facts available together with the debris marker;
- document legacy full-scan completion/cancel/replacement semantics;
- document recycler count, capacity, movement-margin and verification behavior;
- prove whether dispatch is semantically the same V2 asteroid `Добыча газа` side effect;
- add sanitized HTML/JS fixtures and pure parsing/contract tests;
- distinguish no debris in the current opened system from live/CAPTCHA/unreadable failures.

Must not:

- navigate between systems;
- call SendFleet;
- mutate V2/legacy storage;
- add a Qt action.

Acceptance: exact debris detection and dispatch-reuse assumptions are evidence-backed before implementation.

## V2-60 — attach-only current-system debris reader

Read boundary only.

- read only an already-open `galaxy.php` page;
- fail unavailable if the required live page/DOM is absent;
- reuse proven asteroid movement parsing where possible;
- expose typed debris observations containing the debris marker plus exact asteroid trajectory provenance;
- keep `no_debris` separate from CAPTCHA/live unavailable/partial evidence;
- no `refreshGalaxy`, coordinate switching, `goto`, or tab creation.

Acceptance: V2 can identify debris-bearing asteroids in the currently opened system without any game mutation or navigation.

## V2-61 — V2-owned debris evidence / candidate state

No new game side effect.

- persist normalized debris evidence in V2-owned storage;
- preserve provenance: origin coordinate, movement timestamps/period, observed time, evidence source and debris marker facts;
- make exact duplicate ingestion idempotent;
- deterministic current-coordinate projection using the accepted asteroid movement model;
- reject partial/unproven or out-of-range evidence;
- preserve evidence across restart;
- expose typed preview/diff facts for added/kept/duplicate/rejected candidates.

Because V2 does not automatically traverse all 120 systems, do not pretend a current-system read is a completed legacy full scan and do not erase prior proven debris evidence merely because the currently opened system has none.

Acceptance: debris candidate state is deterministic and V2-owned, independent of legacy mutable state.

## V2-62 — debris dispatch reuse gate

No second browser side-effect implementation unless V2-59 proved it necessary.

- map a verified debris candidate to the existing asteroid dispatch preparation/command contract;
- prove the exact target/movement facts remain valid at preparation and pre-click re-check;
- prove recycler mission/capacity selectors and exact new-flight verification are identical to V2-55/V2-58;
- preserve the existing `asteroid_actions` pending/ambiguous restart guard when reuse is valid;
- add tests showing a debris label cannot bypass trajectory/idempotency safety;
- if reuse is not valid, stop this stage and introduce the missing typed boundary/journal gate before any mutation.

Acceptance: debris dispatch has one authoritative mutation boundary, not duplicated browser logic.

## V2-63 — controlled bounded debris dispatch workflow

Explicit application workflow only.

- consume typed V2 debris candidates, never table text;
- bounded multi-selection;
- read-only preparation before confirmation;
- explicit operator confirmation;
- one journaled dispatch attempt per selected candidate through the approved V2 mutation boundary;
- stop the series on first CAPTCHA, ambiguity, error, or manual stop;
- already-started remote attempt is never cancelled mid-flight;
- no retry and no scheduler.

Acceptance: selected debris candidates can be dispatched safely without hidden loops.

## V2-64 — Qt Debris surface

Replace the current placeholder with a real controlled page.

- show V2-owned debris candidate evidence/provenance;
- explicit button to read the already-open current galaxy system;
- multi-select typed candidates;
- preparation preview;
- explicit confirmed dispatch;
- manual Stop semantics consistent with V2-58;
- visible fail-closed states for CAPTCHA/live unavailable/ambiguous/rejected;
- no browser navigation controls disguised as scan actions.

Acceptance: Debris UI is a typed V2 surface and does not directly call CDP/SendFleet.

## V2-65 — debris recovery / discovery hardening

Test and harden at least:

- restart with persisted debris evidence;
- duplicate debris observation;
- asteroid moved before dispatch;
- debris marker missing/partial/unreadable;
- insufficient recyclers;
- full fleet capacity;
- CAPTCHA before and after possible acceptance;
- pending/ambiguous dispatch across restart;
- manual stop / page hide / window close;
- current opened system contains zero debris;
- reading another opened system adds evidence without falsely declaring a full 120-system scan complete.

No automatic navigation or retry may be added to make these cases pass.

Acceptance: restart and failure behavior stays conservative without erasing provenance or opening duplicate-send windows.

## V2-66 — debris parity gate + handoff

No feature expansion unless a safety/parity defect requires it.

- compare the controlled V2 debris outcome with the accepted legacy contracts;
- confirm exact SendFleet verification and journal recovery remain shared/authoritative where reuse was proven;
- run full CI and Qt smoke on final code+docs head;
- update `docs/v2-current-state.md` with exact final squash SHA;
- explicitly record remaining discovery gap: automatic 3×40 traversal is still deferred until a separate browser-navigation contract;
- decide the next batch only after this gate.

Acceptance: debris/recycling execution no longer depends on legacy mutation code, while automatic navigation remains outside scope.

## Explicitly deferred through V2-66

- automatic 3×40 galaxy/system traversal;
- unattended browser launch/navigation;
- asteroid or debris auto-repeat;
- automatic CAPTCHA interaction;
- automatic message deletion;
- default Tkinter → Qt cutover;
- deletion of legacy Tkinter/patch modules.

## Review discipline

For every stage:

1. verify exact current `main` SHA;
2. create a fresh branch;
3. inspect effective call sites before editing;
4. implement/tests within the stage scope;
5. run all three CI jobs;
6. fix substantive P1/P2 findings;
7. squash merge only when green;
8. verify push-CI on the exact squash SHA;
9. only then start the next stage.

If an old source-contract test conflicts with intentional architecture, narrow it to the actual safety invariant; never weaken the invariant itself.
