# V2-66 — debris / recycling parity gate

Date: 2026-08-08

Baseline before V2-66: `fb8628b0c38840936f95fee9d84703969d6e5c13` / PR #100 / V2-65.

Final V2-66 squash:

- `1077125a59a96274017ad09c9814431bdaeb614e`
- PR #101
- exact push-CI run #206 — green on Windows Python 3.10, Windows Python 3.11 and PySide6 offscreen smoke

Scope: final debris parity/recovery gate only. V2-66 did **not** add automatic 3×40 traversal, unattended navigation, debris/asteroid auto-repeat, CAPTCHA interaction, message deletion, launcher cutover or legacy removal.

## Result

The manually controlled V2 debris/recycling path matches the accepted legacy **outcome contract** while intentionally omitting legacy automatic navigation.

Supported V2 path:

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

No debris-specific SendFleet backend and no debris-specific action journal exist.

## Completed debris stages

- V2-59 / PR #94 / `7041ebcee0a96474de9800cf6b454c6e6c9fec6e` — contract audit, sanitized fixtures, exact marker/movement proof, legacy completion/cancel semantics, SendFleet reuse decision.
- V2-60 / PR #95 / `00784ede604a3d4674596b4b8fbe3aa1b620f74e` — attach-only current-system debris reader.
- V2-61 / PR #96 / `84d22044d34c0122506217df6f23ead2b868fa03` — immutable V2-owned debris evidence and deterministic candidates.
- V2-62 / PR #97 / `c8aa2aa9582a107689112b28a48f2173bc900450` — proof and implementation of shared asteroid dispatch/journal reuse.
- V2-63 / PR #98 / `27d0b299cfae9a0ef5f0f4953a80baa8efa9b916` — bounded prepare → explicit single-use confirm → dispatch workflow.
- V2-64 / PR #99 / `1e6726d35f8da6e7dd3c73313028bf890c8080e6` — real Qt Debris page; review corrected the default to legacy debris-specific `debris_recyclers`.
- V2-65 / PR #100 / `fb8628b0c38840936f95fee9d84703969d6e5c13` — restart/recovery/discovery/lifecycle hardening.
- V2-66 / PR #101 / `1077125a59a96274017ad09c9814431bdaeb614e` — final parity/recovery gate.

## Legacy contract versus controlled V2 parity

| Legacy accepted behavior | V2 controlled behavior | Parity decision |
| --- | --- | --- |
| debris marker comes from asteroid `squareInfo` text `Этот астероид содержит обломки` | V2 normalizes the same marker and requires readable movement provenance | parity; V2 fails closed on partial evidence instead of silently treating it as empty |
| debris movement uses normal asteroid movement facts | debris wraps the existing `AsteroidObservationFact` and movement parser/projection | exact shared movement model |
| selected debris dispatch calls legacy `worker.send_asteroid(...)` | debris maps to existing `AsteroidDispatchCommand` / `AsteroidRequestCoordinator` | exact side-effect reuse; no duplicate backend |
| recycler mission is `8` / `Добыча газа` | authoritative asteroid backend retains and verifies the same mission | parity |
| recycler count is operator-configured | Qt Debris uses debris-specific legacy `debris_recyclers` default plus typed operator value | parity |
| capacity/recycler inventory/movement margin gate sending | shared preparation plus final live pre-click recheck | parity with stronger last-moment validation |
| completed legacy full scan replaces saved debris results | V2 has no approved full traversal, so current-system reads are append-only and cannot erase other systems | intentional non-parity required by attach-only boundary |
| cancelled legacy scan does not replace previous completed set | partial/CAPTCHA/unavailable V2 reads are not ingested as completed evidence | conservative parity |
| legacy scan traverses galaxies 1–3, systems 40→1 | V2 reads only the system the operator already opened | explicitly deferred; never falsely reported as a completed 120-system scan |

## Authoritative shared mutation boundary

V2-59 and V2-62 proved that debris changes discovery/provenance, not the remote effect.

The authoritative chain is:

1. `DebrisCandidate` preserves exact `DebrisObservationFact` + underlying `AsteroidObservationFact`;
2. `asteroid_command_from_debris(...)` maps it to `AsteroidDispatchCommand` without a debris retry label;
3. `DebrisEnabledApplicationContext` creates `AsteroidRequestCoordinator(self._asteroid_actions, database)` using the **same** asteroid action service and V2 database;
4. unresolved identity stays the existing `asteroid_actions` trajectory identity;
5. `V2AsteroidCdpBackend` performs fresh trajectory, recycler, capacity, target-form and CAPTCHA checks immediately before mutation;
6. there is one SendFleet implementation;
7. verification requires a new fleet ID + exact source + exact target + mission `Добыча газа`.

A different UI label, request ID or recycler count cannot open a second namespace after a `pending` or `ambiguous` trajectory. Regression coverage proves a generic asteroid ambiguous request blocks a later debris-labelled request before another backend dispatch.

## Recovery / failure matrix

| Case | Required V2 outcome |
| --- | --- |
| restart with persisted debris evidence | immutable marker-positive evidence survives |
| exact duplicate observation | idempotent insert |
| current system has zero debris | `no_debris` for that system only; other evidence remains |
| another manually opened system is read | evidence accumulates; no full-scan claim |
| marker missing but movement readable | proven current-system `no_debris` |
| marker present but movement partial/unreadable | `partial_evidence`; not ingestible |
| asteroid moved before mutation | failed-safe stop; no retry |
| insufficient recyclers | failed-safe stop; no retry |
| fleet capacity full | failed-safe stop; no retry |
| CAPTCHA before acceptance | stop/failed-safe; no CAPTCHA interaction |
| CAPTCHA/unknown after possible acceptance | `ambiguous`; no inferred retry |
| crash after durable pending commit | `pending` survives restart and blocks second effect |
| ambiguous across restart | `ambiguous` survives and blocks second effect |
| manual Stop during series | started attempt settles; next candidate does not start |
| page hide / input / selection change | unconfirmed preparation is disarmed; running series requests Stop before next candidate |
| window/context close | request Stop for next candidate + disarm unconfirmed preparation |

## Qt boundary

The real Debris page is a V2 application surface, not a browser driver. It calls context-level operations for candidate preview, current-system read, evidence ingestion, read-only preparation, explicit confirmation and Stop/cancel lifecycle.

The page does not import/use Playwright, CDP backends, SendFleet selectors, `goto`, `refreshGalaxy`, system-switching APIs or `ajax_galaxy.php` traversal.

The UI explicitly states that it reads the manually opened system and does not perform automatic 3×40 traversal.

## Storage and launcher parity

Legacy SQLite remains strictly read-only through `mode=ro` + `PRAGMA query_only=ON`.

Debris evidence is V2-owned in additive `debris_observations`. Core schema version remains **8**.

Default launcher remains:

```text
run_app.bat -> app_entry.py
```

PySide6 remains opt-in through `app_qt.py`.

Rollback refs and legacy implementation remain untouched.

## Explicitly deferred after V2-66

- automatic 3×40 galaxy/system traversal;
- unattended `goto`, `refreshGalaxy`, system switching, tab creation or browser launch;
- debris auto-repeat / scheduler;
- asteroid auto-repeat / scheduler;
- CAPTCHA solve/click/bypass;
- automatic message deletion;
- default Tkinter → Qt cutover;
- legacy code deletion.

The 2026-08-06 Rest Mode concept cannot be implemented literally under the current baseline because it assumes automatic opening/refreshing of Flights. The next prepared batch therefore begins with a separate browser navigation/read ownership contract audit rather than smuggling navigation into Rest Mode or debris.

## Final gate verification

Final PR #101 head passed:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke;
- substantive review finding about an over-broad scheduler source-contract was corrected to real executable/state symbols and resolved.

After squash merge, push-CI run #206 passed the same three jobs on the exact V2-66 squash `1077125a59a96274017ad09c9814431bdaeb614e`.

V2-66 is therefore closed. The follow-up docs-only handoff may change `main`, but the final debris action baseline remains the exact squash above.
