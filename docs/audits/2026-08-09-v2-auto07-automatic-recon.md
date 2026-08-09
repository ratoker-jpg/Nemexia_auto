# AUTO-07 — automatic exact-fleet reconnaissance

Date: 2026-08-09

Baseline: `20a6b8196b25e7b0d4abae667e9b7a7440e7316f` (corrective PR #135 after Browser Readiness UI, exact post-main push CI #326 green).

## Goal

Remove the normal requirement to type an exact Spy fleet ID when the live DOM can prove a processable existing espionage fleet.

AUTO-07 does **not** create a new espionage route. AUTO-01 did not prove that effective legacy creates one when no existing processable spy fleet exists, so AUTO-08 remains audit/no-invention territory.

## Single owned page

Automatic recon uses the same `V2AutomaticReconCdpBackendNoAutoReconnect` instance for:

- `NavigationCoordinator` page ownership;
- exact spy-fleet discovery;
- exact one-attempt `processSpy(fleet_id)` mutation;
- rendered System-message evidence reads.

It never creates or owns a second hidden Fleets/Options tab.

Sequence:

```text
ensure Fleets through BrowserReadinessManager
→ verify page token + account + selected PlanetIdentity
→ discover exact spy1Link-<fleet_id> + spy1Time-<fleet_id>
→ choose one proven-ready fleet deterministically
→ ensure System messages through NavigationCoordinator
→ capture baseline report IDs
→ ensure Fleets again
→ re-verify same account/planet/page token
→ revalidate exact fleet route + ready timer
→ persist immutable automatic-recon pending request
→ call processSpy(<fleet_id>) exactly once
→ ensure System messages
→ verify new report ID + exact target + fresh timestamp
→ verified / ambiguous
```

## Exact DOM evidence

Infrastructure is allowed to use the supplied browser-reference contract:

```text
#spy1Link-<fleet_id> / processSpy(<fleet_id>)
#spy1Time-<fleet_id>
closest('tr') → source + target
```

The application layer contains no Playwright/CDP calls or selectors.

A fleet is processable only when:

- its exact link ID yields an exact fleet ID;
- its exact `onclick` is `processSpy(<same_id>)`;
- source and target coordinates come from the same closest row;
- the matching exact timer is parseable and has reached zero;
- the same evidence is re-read immediately before the persistent mutation journal is opened.

Missing or future timer evidence is not guessed as ready.

## Exactly-one safety

`automatic_recon_actions` is V2-owned persistent state with immutable request IDs and terminal states:

- `verified`;
- `ambiguous`;
- `failed_safe`.

Before the remote mutation:

- preflight failures are `failed_safe`;
- CAPTCHA is STOP;
- no `processSpy` has been attempted.

Once the exact `window.processSpy(Number(fleetId))` evaluation begins:

- transport/evaluation uncertainty is `ambiguous`;
- there is no automatic retry;
- unresolved `pending/ambiguous` AUTO-07 state blocks a new automatic request.

Manual exact-fleet spy and AUTO-07 are interlocked in both directions. An unresolved request in either journal blocks the other mutation path. AutoFarm also counts unresolved automatic recon as a blocking side effect.

Bulk `processSpy(0)` is not restored.

## Verified report and refill

Verification requires all of:

- report/message ID not present in the baseline;
- exact target equal to the selected fleet target;
- normalized fresh timestamp at/after the mutation window with a small clock-tolerance allowance.

A verified result then enters the already-existing controlled pipeline:

```text
verified report
→ V2 recon ingest
→ deterministic AutoFarm queue refill
```

`ControlledReconRefill(fleet_id=None)` selects AUTO-07. Passing an explicit fleet ID keeps the existing compatibility path until the separate UI-only follow-up removes manual fleet-ID entry from normal UX.

## Scope boundaries

This automation PR intentionally does not change `v2/ui/*`.

Not included:

- no new espionage SendFleet route;
- no `processSpy(0)`;
- no message deletion;
- no CAPTCHA solve/click/bypass;
- no galaxy/system navigation (AUTO-09);
- no 3×40 traversal (AUTO-10);
- no restart/session-loss recovery beyond current fail-closed semantics (AUTO-13);
- no UI consolidation or visual polish.

## AUTO-07 acceptance

AUTO-07 is complete only when:

- exact ready fleet discovery is deterministic and tested;
- one successful run invokes exactly one exact `processSpy(fleet_id)`;
- post-attempt uncertainty persists `ambiguous` and a second request cannot retry;
- pre-attempt failure persists `failed_safe`;
- manual and automatic spy journals cannot open concurrent unresolved mutation windows;
- verified result flows through existing recon ingest/refill;
- production shares NavigationCoordinator's one owned page;
- full CI is green;
- substantive P1/P2 review findings are resolved;
- squash merge is followed by exact green post-main push CI.

After that, remove the manual fleet-ID normal UX in a separate UI-only PR, then proceed to AUTO-08.
