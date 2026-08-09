# AUTO-01 — effective legacy automation parity audit

Date: 2026-08-09

Baseline:

- `6e1c92a866bd201ca73c84335a73e4bd03d10fbe`
- squash PR #127 — `docs: add browser reference and full automation roadmap`
- exact post-merge CI #292 — green

Scope: **RESEARCH ONLY**. This audit does not add browser navigation, page creation, planet switching, `refreshGalaxy`, background loops, Rest Mode, fleet mutation, message deletion, or any other live behavior.

Primary contract: `docs/plans/2026-08-09-v2-full-automation-ui-consolidation.md`.

## Decision

The previous `NO NAVIGATION BOUNDARY` was a correct migration safety gate, but it is not feature parity with the effective legacy runtime.

The effective legacy application already removes substantial browser-servicing work from the operator: it can start the dedicated browser, bind one Nemexia page, create/open game pages, switch own planets, prepare `fleets.php`, prepare `options.php` System messages, prepare `galaxy.php`, switch galaxy systems through `refreshGalaxy()`, scan asteroid/debris systems, run AutoFarm background cycles and continue asteroid autorenew after persisted state.

V2 deliberately removed those behaviors while it established typed action journals and fail-closed mutation semantics. The next stages must restore the useful automation **through new V2 ownership, identity and journaling contracts**, not by copying the legacy monkey patches.

The new user browser reference closes an important evidence gap: own planets are represented by `#planetSwitch`, `#planetsListHolder` and `change_planet.php?id=<planet_id>` anchors, with selected-state evidence and stable internal planet IDs. That is sufficient to start AUTO-02 identity modeling. It does **not** by itself authorize navigation mutation; AUTO-03/AUTO-04 still need a central exactly-once coordinator and persistent context journal first.

## Effective legacy runtime composition

`app_entry.py` installs browser patches before importing `app.py` in this order:

```text
install_bound_tab_fix()
install_ship_retry_fix()
install_raid_verification_fix()
install_background_browser_fix()
import app as app_module
```

Later installers add the effective farm/debris/runtime behavior. Therefore parity is measured against the composite runtime, not raw `browser.py` in isolation.

Relevant effective behavior:

- `bound_tab_fix.py` binds one explicitly selected live Nemexia `Page` object after Connect and refuses silent rebinding;
- `background_browser_fix.py` replaces browser launch and page preparation so the bound tab can work while minimized without `bring_to_front()`;
- `resource_farm_auto.py` replaces the legacy auto cycle with the 500k-resource loop;
- `debris_asteroids_feature.py` adds the debris workflow;
- `browser.py` remains the source for planet switching, galaxy/system loading, report collection, fleet send, asteroid scan/send and CAPTCHA detection.

Legacy page ownership is useful but weaker than the required V2 contract: a live Playwright object plus host membership does not prove account identity, planet identity or persisted before/after context.

## Effective legacy automation parity matrix

| LEGACY FEATURE | CURRENT V2 | MISSING | REQUIRED V2 CONTRACT | RISK | IMPLEMENTATION ORDER |
|---|---|---|---|---|---|
| Dedicated browser start | Legacy can locate Yandex, start it with CDP/profile flags and open `fleets.php`; background patch disables browser background throttling. | V2 only attaches to an already-running CDP endpoint. | BrowserSession owns launch-or-attach state without taking ownership of user browser shutdown; explicit executable/profile/CDP evidence; CAPTCHA remains visible/manual. | Medium | AUTO-02 foundation, activation through AUTO-05/AUTO-06 |
| Browser connect and page ownership | Explicit Connect binds one active Nemexia page; ambiguous multiple active tabs fail. | V2 readers independently scan for first URL match and have no shared bound page identity. | One BrowserSession with exact runtime page binding, server evidence and invalidation when page/account context changes. | High | AUTO-02 → AUTO-03 |
| Create/select game tab | Raw legacy connect may create a page and `goto(fleets.php)` when no game page exists; effective bound runtime then keeps one page. | V2 never creates tabs/pages. | Only NavigationCoordinator may create/choose a game surface; page identity must be journaled and verified before use. | High | AUTO-03 → AUTO-05 |
| Enumerate owned planets | Legacy reads `#planetsListHolder`; most legacy call sites reduce identity to coordinates. | V2 currently exposes only coordinate strings from link text. | First-class `PlanetIdentity`: internal planet ID, coord, display name, selected proof, server/account ownership evidence. Account identity may use a deterministic ownership fingerprint when no stronger player identifier is available. | High | AUTO-02 |
| Selected planet proof | Legacy reads `#my_c1/#my_c2/#my_c3` or `#planetSwitch`. | V2 has no typed selected-planet identity. | Selected planet must be proven from game-owned DOM and tied to AccountContext/BrowserSession. | High | AUTO-02 |
| `change_planet.php` | Legacy searches own-planet anchors, performs one `page.goto(link)` and verifies the resulting coordinate. | Prohibited by current V2 boundary. | NavigationCoordinator-only planet switch; immutable request ID; before/intent/after journal; exactly one remote navigation attempt; account + expected internal planet ID/coord verification; ambiguous result blocks automatic retry. | Critical | AUTO-03 → AUTO-04 |
| Prepare `fleets.php` | Legacy automatically opens it when required and verifies main DOM/CAPTCHA. | User must manually open `fleets.php`. | Coordinator page-preparation command with same account/planet before and after, typed page-kind proof and no feature-level selectors. | High | AUTO-05 |
| Prepare `options.php` / System messages | Legacy automatically navigates to `options.php`, calls `loadTabContent('TabAdministrative',2,...)` / `showTab`, and paginates reports. | User must manually open `options.php` and pre-render System messages. | Coordinator prepares page + System tab and verifies `TabAdministrative` readiness, account/planet stability and CAPTCHA. | High | AUTO-05 |
| Prepare `galaxy.php` | Legacy selects requested own planet, opens galaxy page and verifies galaxy DOM. | User must manually open `galaxy.php` on the intended context. | Coordinator prepares galaxy surface only after account/planet proof; page-kind verification is separate from system selection. | High | AUTO-05 |
| `refreshGalaxy()` / `ajax_galaxy.php` | Legacy writes `#c1/#c2`, invokes `refreshGalaxy()`, waits for POST `ajax_galaxy.php`, loader completion and requested values. | Completely prohibited in current V2. | Exactly-one journaled system-navigation mutation; verify bound page, account, selected planet, requested galaxy/system and settled holder after the request; no automatic retry after uncertain response. | Critical | AUTO-09 |
| Existing spy fleet discovery | Legacy bulk flow does not require operator to type a fleet ID; existing espionage rows expose processable actions. | V2 exact-fleet action is safe but manual fleet ID is entered by user. | Read-only discovery of exact processable `spy1Link-<fleet_id>` / `processSpy(<fleet_id>)`, source and target from the same row; no text-only identity. | High | AUTO-07 |
| Process existing espionage fleet | Legacy calls `processSpy(0)` for all existing spy fleets; V2 correctly proved exact `processSpy(<fleet_id>)` semantics instead. | V2 cannot automatically choose/process the next proven fleet. | Keep V2 safer exact-fleet mutation: immutable request ID, exactly one `processSpy(fleet_id)`, fresh target-matching report verification, ambiguous=no retry. Do **not** restore bulk `processSpy(0)` merely for parity. | Critical | AUTO-07 |
| Create a new espionage route | **Not proven in effective legacy runtime.** Repository code exposes processing existing espionage fleets, not a mission-2 SendFleet workflow for creating a new spy route. | No V2 route creation. | No implementation unless new evidence proves the exact legacy route. If later proven, use a separate typed send journal with exact fleet verification. | Critical | AUTO-08 = contract/no-op unless evidence changes |
| Read fresh spy reports | Legacy auto-prepares System messages, paginates, parses reports and AutoFarm uses the result. | V2 can parse already-rendered reports but requires manual page preparation. | Readiness + coordinator prepare System page, then current V2 report ingestion/refill pipeline. | Medium | AUTO-05 → AUTO-07 |
| Selective spy-message cleanup | Legacy AutoFarm deletes only recognized old spy message IDs, excluding protected coordinates, before requesting fresh reports. | V2 intentionally performs no automatic message deletion. | Cleanup is not required to service the browser if V2 can distinguish fresh reports. If ever migrated, it must be a separate exact-ID journaled destructive action; never `deleteAllMessages`, never required for recovery. | Critical | Not a prerequisite; reconsider only after AUTO-07 evidence |
| AutoFarm background loop | Effective legacy waits for attack returns, refreshes spy data, rebuilds target queue, sends up to free slots and repeats; it is disarmed on process start until user enables it. | V2 has FarmController/queue/actions but no unattended browser-readiness/navigation loop. | V2 scheduler orchestrates existing safe services through Readiness/NavigationCoordinator; preserves disarmed startup, slot accounting, CAPTCHA STOP and exactly-one action journals. | Critical | AUTO-06 → AUTO-07 → AUTO-13/AUTO-14 |
| Asteroid scan | Legacy automatically selects home, opens galaxy, traverses configured systems downward, reads `squareInfo`, calculates movement and sends verified recycler missions. | V2 reads/actions exist but browser system must already be prepared; no automatic traversal. | Navigation-owned deterministic scan state, persisted progress, stop/captcha semantics, no implicit completion. | High | AUTO-09 → AUTO-10 |
| Debris 3×40 discovery | Implemented legacy contract: galaxies `1,2,3`, systems `40→1`, exactly 120 systems; completed scan replaces previous persisted list, cancelled/incomplete scan does not. | V2 only reads current prepared galaxy/system and cannot traverse. | Persisted scan run/cursor with deterministic `1:40 … 3:1` progress (or an explicitly documented equivalent order), last-complete preservation, cancellation and restart semantics. | High | AUTO-10 |
| Asteroid autorenew / repeat | Legacy persists asteroid auto state and next cycle; after a successful wave it schedules latest `return_at + buffer` (default 5 min), checks CAPTCHA while waiting and can continue after restart. | V2 deliberately has no unattended asteroid scheduler. | Explicit Start/Stop persisted scheduler; recovery from restart; before every cycle re-establish Browser/Account/Planet/Page readiness; CAPTCHA permanently pauses until manual resume; action journals remain exactly-once. | Critical | AUTO-11 → AUTO-13 |
| Debris repeat | Legacy debris contract explicitly says **no automatic repeat cycles**. | V2 has no debris repeat. | Do not invent a debris autorenew loop under the name of parity. Manual/repeated scans may be user-triggered only unless a later product contract changes this. | Medium | AUTO-11 no-op for debris repeat |
| Rest Mode | **Not implemented in effective legacy runtime.** `docs/plans/2026-08-06-rest-mode-and-attack-watch.md` is explicitly a future product concept; no retained runtime module implements it. | V2 has no Rest Mode. | AUTO-12 is a new approved product feature, not legacy parity: 5-minute watcher, incoming attack/activity timer reads, notifications, browser mutex, CAPTCHA STOP, no fleet mutation. Requires NavigationCoordinator first. | High | AUTO-12 |
| Background browser operation | Legacy background patch removes foreground activation and disables Chromium background throttling; AutoFarm and asteroid autorenew operate through the bound page. | V2 has no central background browser owner. | One coordinator mutex; background tasks request page/context readiness through it and never manipulate Playwright/CDP directly from UI/features. | High | AUTO-03 → AUTO-06 → AUTO-11/AUTO-12 |
| Context restoration before workflow | Legacy frequently reselects home planet and required page before fleet/galaxy work, but only verifies coordinate/host and has no account journal. | V2 avoids navigation rather than restoring context. | Reconstruct desired account/planet/page from persisted typed state; prove before/after account and planet identity; manual changes invalidate prepared intents. | Critical | AUTO-03 → AUTO-05 → AUTO-13 |
| CAPTCHA | Legacy detects recaptcha/BOTCHECK/known text and stops; no solving/bypass. V2 already uses fail-closed CAPTCHA handling. | Readiness currently exposes technical/manual errors instead of one global automation stop state. | Preserve CAPTCHA = STOP globally. No solve, click, bypass or automatic Continue. Persist stop reason so background loops cannot continue underneath it. | Critical | Preserve in every AUTO stage; UX in AUTO-06/12/13 |
| Ambiguous remote effect / recovery | Legacy has several local safeguards and avoids duplicate resend when a send may have succeeded, but navigation has no immutable persistent journal. V2 fleet action journals are stronger. | Browser context mutations have no V2 recovery model because they do not yet exist. | Persistent navigation/context journal; pending→verified/ambiguous/failed-safe; no second attempt after uncertain effect; reconcile only from read evidence. | Critical | AUTO-03 → AUTO-04/05/09 → AUTO-13 |
| Restart recovery | Legacy asteroid autorenew persists next-cycle state; other browser ownership is runtime-only and requires reconnect/rebinding. | V2 action recovery exists, browser/session/navigation recovery does not. | On restart, never assume old page ownership; reattach, rebuild BrowserSession/AccountContext, reconcile journal from observable facts, require manual intervention when identity is insufficient. | Critical | AUTO-13 |

## What AUTO-01 changes about the old NO NAVIGATION decision

The old audit correctly rejected navigation because the repository could not prove account/planet ownership strongly enough. The 2026-08-09 browser reference now adds stable evidence for the own-planet surface:

```text
#planetSwitch
#planetsListHolder
change_planet.php?id=<planet_id>
li.active
```

This authorizes **identity research and modeling in AUTO-02**, not direct navigation.

The safe reopening sequence is:

```text
AUTO-02 typed read-only identity
→ AUTO-03 central coordinator + persistent journal
→ AUTO-04 one verified planet-switch primitive
→ AUTO-05 verified page preparation
→ checkpoint
→ AUTO-06+ workflows
```

Skipping AUTO-02/AUTO-03 and reusing legacy `page.goto()` directly would recreate the exact ownership/recovery gap that V2 was designed to remove.

## Browser/account identity conclusion for AUTO-02

The repository does not currently prove a stable textual player/account ID selector across all supplied pages. AUTO-02 must therefore avoid fabricating one.

A valid first AccountContext can be built from evidence the game does own:

- exact game server/host;
- one bound live page/session;
- complete own-planet membership from `#planetsListHolder`;
- internal planet IDs + coordinates;
- deterministic ownership fingerprint over the sorted own-planet set;
- selected planet proof.

If a stronger account/player identifier is later observed, it can be added without changing PlanetIdentity semantics. Navigation must fail closed if the ownership fingerprint changes unexpectedly.

## Spy-route conclusion for AUTO-08

Do **not** implement a new espionage fleet send merely because mission value `2` is visible in the browser reference.

The effective legacy Python runtime proves:

```text
process existing espionage fleet → processSpy(fleet_id or legacy bulk 0)
```

It does not prove:

```text
select spy ships → mission 2 → target → SendFleet → verified new espionage route
```

AUTO-08 therefore remains an explicit parity gate/no-op unless new saved-page or runtime evidence proves that route creation was part of effective legacy behavior.

## Rest Mode conclusion for AUTO-12

Rest Mode is not an effective-legacy feature at this baseline. Its repository document is explicitly marked a future product concept. AUTO-12 remains authorized by the new roadmap, but it must be reported as a **new implementation of an approved contract**, not as recovered legacy parity.

This distinction matters for AUTO-14: full *legacy automation parity* can be reached without pretending Rest Mode existed previously, while the final roadmap can still require Rest Mode before the overall automation program is called complete.

## Manual work that still exists after AUTO-01

AUTO-01 intentionally changes no runtime. The user still has to service the browser exactly as before this audit, including where applicable:

- start/connect a CDP browser for V2;
- open `fleets.php`;
- open `options.php` and render System messages;
- open `galaxy.php` on the intended context;
- choose the intended own planet manually;
- position the intended galaxy/system manually;
- enter an exact processable spy fleet ID manually for the current V2 spy action;
- restart/prepare browser context after page/session loss.

AUTO-01 therefore **must not** be described as automation parity progress in the user workflow. It is the evidence gate that makes AUTO-02 safe to start.

## Required implementation order

1. **AUTO-02** — `BrowserSession` / `AccountContext` / `PlanetIdentity`, read-only.
2. **AUTO-03** — one `NavigationCoordinator`, mutex and persistent context journal.
3. **AUTO-04** — verified planet switching.
4. **AUTO-05** — verified fleets/System/galaxy page preparation, then exact manual-work checkpoint.
5. **AUTO-06** — Browser Readiness Manager.
6. **AUTO-07** — automatic exact-fleet recon acquisition; keep current safer exact-fleet mutation.
7. **AUTO-08** — no-op unless new proof of actual legacy espionage-route creation appears.
8. **AUTO-09** — verified `refreshGalaxy` system navigation.
9. **AUTO-10** — deterministic controlled 3×40 discovery.
10. **AUTO-11** — asteroid autorenew parity only; do not invent debris repeat.
11. **AUTO-12** — approved Rest Mode product contract after navigation ownership.
12. **AUTO-13** — browser/context/restart recovery.
13. **AUTO-14** — rerun this matrix and block parity claim on remaining required manual browser servicing.

UI consolidation and visual QA remain separate UI-only PRs and must not be mixed into these automation/business changes.

## Safety invariants carried forward

Every implementation stage must preserve all of these:

- CAPTCHA = STOP; never solve/click/bypass;
- immutable request IDs for remote/context mutations;
- exactly one remote mutation attempt per request;
- no automatic retry after ambiguous remote effect;
- persistent journals for mutations that can outlive the process;
- account/planet/page before-and-after verification;
- manual browser/account/planet changes invalidate prepared intents;
- legacy SQLite stays read-only from V2;
- V2 migrations remain versioned/additive;
- `run_legacy.bat` rollback stays supported;
- UI never imports Playwright/CDP selectors;
- no migration of `processSpy(0)` merely to match legacy convenience;
- no automatic `deleteAllMessages`;
- no invented debris repeat or invented spy-route creation.

## AUTO-01 acceptance

AUTO-01 is complete when this audit is merged with green full CI and no substantive unresolved P1/P2 review findings.

No navigation mutation is authorized inside AUTO-01 itself. The next implementation stage is AUTO-02 from a freshly verified post-merge `main`.