# V2-66 — debris / recycling parity gate

Date: 2026-08-08

Baseline before V2-66: `fb8628b0c38840936f95fee9d84703969d6e5c13` / PR #100 / V2-65.

Scope: final debris parity/recovery gate only. This stage does **not** add automatic 3×40 traversal, unattended navigation, debris/asteroid auto-repeat, CAPTCHA interaction, message deletion, launcher cutover, or legacy removal.

## Result

The manually controlled V2 debris/recycling path now matches the accepted legacy **outcome contract** while intentionally omitting legacy automatic navigation.

The supported V2 path is:

```text
already-open galaxy.php
→ attach-only current-system squareInfo read
→ exact debris marker + immutable asteroid movement provenance
→ append-only V2-owned debris evidence
→ deterministic current-coordinate candidate projection
→ bounded typed multi-selection
→ read-only shared asteroid preparation
→ explicit single-use operator confirmation
→ shared asteroid_actions unresolved-trajectory journal
→ fresh live trajectory/recycler/capacity/CAPTCHA re-check
→ exactly one shared asteroid SendFleet attempt
→ exact new fleet ID + source + target + mission Добыча газа verification
→ verified / ambiguous / failed-safe
```

No debris-specific SendFleet backend or debris-specific action journal exists.

## Completed debris stages

- V2-59 / PR #94 / squash `7041ebcee0a96474de9800cf6b454c6e6c9fec6e` — contract audit, sanitized fixtures, exact marker/movement proof, legacy completion/cancel semantics, SendFleet reuse decision.
- V2-60 / PR #95 / squash `00784ede604a3d4674596b4b8fbe3aa1b620f74e` — attach-only current-system debris reader.
- V2-61 / PR #96 / squash `84d22044d34c0122506217df6f23ead2b868fa03` — immutable V2-owned debris evidence and deterministic candidates.
- V2-62 / PR #97 / squash `c8aa2aa9582a107689112b28a48f2173bc900450` — proof and implementation of shared asteroid dispatch/journal reuse.
- V2-63 / PR #98 / squash `27d0b299cfae9a0ef5f0f4953a80baa8efa9b916` — bounded prepare → explicit confirm → dispatch workflow.
- V2-64 / PR #99 / squash `1e6726d35f8da6e7dd3c73313028bf890c8080e6` — real Qt Debris page; review also corrected the legacy default to `debris_recyclers`.
- V2-65 / PR #100 / squash `fb8628b0c38840936f95fee9d84703969d6e5c13` — restart/recovery/discovery/lifecycle hardening.

The exact V2-66 squash SHA cannot be embedded in the commit before that commit exists. As with the V2-58→PR #93 handoff, it must be pinned immediately after the V2-66 squash merge and exact push-CI in a docs-only handoff/current-state update.

## Legacy contract versus controlled V2 parity

| Legacy accepted behavior | V2 controlled behavior | Parity decision |
| --- | --- | --- |
| debris marker comes from asteroid `squareInfo` text `Этот астероид содержит обломки` | V2-59/60 normalizes the same marker and requires readable movement provenance | parity; V2 fails closed on partial evidence instead of silently treating it as empty |
| debris asteroid movement uses the normal asteroid movement facts | V2 composes debris evidence around `AsteroidObservationFact` and the existing movement parser/projection | exact shared movement model |
| selected debris dispatch calls legacy `worker.send_asteroid(...)` | debris candidate maps to existing `AsteroidDispatchCommand` / `AsteroidRequestCoordinator` | exact side-effect reuse; no duplicate backend |
| recycler mission is `8` / `Добыча газа` | authoritative asteroid backend retains the same mission and verifies exact new flight | parity |
| recycler count is operator-configured | Qt Debris uses debris-specific legacy `debris_recyclers` default and typed spinbox value | parity |
| fleet capacity/recycler inventory/movement margin gate sending | shared asteroid preparation plus final live pre-click snapshot rechecks all three | parity with stronger last-moment validation |
| completed legacy full scan replaces previous saved debris results | V2 has no approved full traversal, so a current-system read is append-only and cannot erase evidence from other systems | intentional non-parity required by attach-only safety boundary |
| cancelled legacy scan does not replace previous completed persisted set | V2 partial/CAPTCHA/unavailable reads are not ingested as completed evidence | equivalent conservative outcome |
| legacy automatic scan traverses galaxies 1–3, systems 40→1 | V2 reads only the system the operator already opened | explicitly deferred; never falsely reported as completed 120-system scan |

## Authoritative shared mutation boundary

V2-59 and V2-62 proved that debris changes discovery/provenance, not the remote effect.

The authoritative mutation chain remains:

1. `DebrisCandidate` preserves the exact `DebrisObservationFact` and underlying `AsteroidObservationFact`;
2. `asteroid_command_from_debris(...)` maps that candidate to `AsteroidDispatchCommand` without a debris retry label;
3. `DebrisEnabledApplicationContext` constructs `AsteroidRequestCoordinator(self._asteroid_actions, database)` from the **same** asteroid action service and V2 database;
4. unresolved identity remains the existing `asteroid_actions` trajectory identity;
5. the real `V2AsteroidCdpBackend` performs fresh trajectory, recycler, capacity, target-form and CAPTCHA checks immediately before mutation;
6. there is one authoritative SendFleet implementation;
7. verification requires a new fleet ID plus exact source, target and mission `Добыча газа`.

A different UI label, request ID or recycler count cannot open a second namespace after a `pending` or `ambiguous` trajectory. Regression coverage explicitly starts a generic asteroid ambiguous request and proves a debris-labelled request is blocked before another backend dispatch.

## Recovery / failure matrix

| Case | Evidence / regression | Required outcome |
| --- | --- | --- |
| restart with persisted debris evidence | `tests/test_v2_debris_repository.py` | immutable marker-positive evidence survives restart |
| exact duplicate observation | debris observation unique identity + repository tests | idempotent insert; no duplicated persisted fact |
| current system has zero debris | `DebrisReadState.NO_DEBRIS` + repository no-op | old evidence from other systems remains untouched |
| another manually opened system is read | repository accumulation test | new evidence is added; no completed-full-scan claim |
| marker missing but squareInfo/movement readable | V2-60/V2-65 reader tests | proven `no_debris` for that current system only |
| marker present but movement partial/unreadable | V2-60/V2-65 reader tests | `partial_evidence`; not `no_debris`, not ingestible |
| asteroid moved before mutation | shared live pre-click trajectory gate + V2-65 failed-safe regression | reject before/at mutation boundary; no retry loop |
| insufficient recyclers | shared final recycler snapshot + V2-65 regression | failed-safe stop; no retry loop |
| fleet capacity full | shared final capacity snapshot + V2-65 regression | failed-safe stop; no retry loop |
| CAPTCHA before acceptance | shared prepare/pre-click detection + V2-65 regression | stop/failed-safe; CAPTCHA never interacted with |
| CAPTCHA or unknown state after possible acceptance | shared post-send verification + ambiguous classification | `ambiguous`; never infer safe retry |
| crash after pending commit | V2-65 simulated `BaseException` crash window | durable `pending` survives restart and blocks a second effect |
| ambiguous across restart | V2-65 restart regression | durable `ambiguous` blocks a second effect |
| manual Stop during series | V2-63 workflow regression | current started attempt settles; next candidate never starts |
| page hide / input or selection change | V2-65 lifecycle disarm | stop future series work and remove stale unconfirmed token |
| window/context close | V2-65 context close hardening | request Stop for next candidate + disarm unconfirmed preparation |

## Qt boundary

The real Debris page is a V2 application surface, not a browser driver.

It calls only context-level operations for:

- candidate preview;
- current-system read;
- evidence ingestion;
- read-only preparation;
- explicit confirmation;
- manual Stop/cancel-preparation lifecycle.

The page does not import/use Playwright, CDP backends, SendFleet selectors, `goto`, `refreshGalaxy`, system-switching APIs, or `ajax_galaxy.php` traversal.

The UI explicitly tells the operator that it reads the manually opened system and does not perform automatic 3×40 traversal.

## Storage and launcher parity

Legacy SQLite remains strictly read-only through the existing `mode=ro` + `PRAGMA query_only=ON` boundary.

Debris evidence is V2-owned in additive `debris_observations` storage. The core V2 schema version remains **8**; the feature-local table does not modify legacy SQLite.

Default launcher remains:

```text
run_app.bat -> app_entry.py
```

PySide6 remains opt-in through `app_qt.py`.

Rollback refs and legacy implementation remain untouched.

## Explicitly deferred after V2-66

Still outside the debris parity gate:

- automatic 3×40 galaxy/system traversal;
- any unattended `goto`, `refreshGalaxy`, system switching, tab creation or browser launch;
- debris auto-repeat / scheduler;
- asteroid auto-repeat / scheduler;
- CAPTCHA solve/click/bypass;
- automatic message deletion;
- default Tkinter → Qt cutover;
- deletion of legacy code.

The existing 2026-08-06 Rest Mode product concept cannot be implemented literally under the current baseline because it assumes automatic opening/refreshing of the Flights page. A future implementation must first establish a separate browser-navigation/read ownership contract rather than smuggling navigation into debris or rest-mode work.

## Gate verification

V2-66 is mergeable only after the final code+docs head passes all existing gates:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke;
- no unresolved substantive P1/P2 review findings.

After squash merge, push-CI must be green on the **exact** V2-66 squash SHA before the docs-only handoff pins that SHA and prepares any next implementation batch.
