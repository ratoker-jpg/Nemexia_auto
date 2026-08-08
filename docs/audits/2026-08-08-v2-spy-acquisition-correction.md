# V2-45 — correction to the spy acquisition contract

Date: 2026-08-08

Baseline entering V2-45: `e02418348beb1ee9240b0c30fa7afaaf92cc0dbd`.

## Correction

V2-41 correctly identified the legacy call `processSpy(0)`, but its interpretation as a target/probe request was not sufficiently proven. V2-43 and V2-44 therefore created a conservative typed/journal boundary before any real mutation, but modeled `source + target + probe_count`.

Before enabling the first real mutation, the saved `fleets.php` evidence was re-inspected. It proves a different game contract:

```html
<tr class="espionageClass">
  <td>3:39:11</td>
  <td>2:22:19</td>
  ...
  <a id="spy1Link-152272" onclick="processSpy(152272)">Шпионаж</a>
</tr>
```

The side-effect identity is therefore an **already-existing espionage fleet ID**. `processSpy(fleet_id)` processes that exact row. `processSpy(0)` is the legacy bulk form over existing spy rows; it is not evidence of dispatching arbitrary probe ships to a caller-supplied target.

V2 must not invent probe availability, ship keys, or a target-dispatch API that has not been proven.

## V2-45 contract

The typed command is now:

```text
SpyRequestCommand(fleet_id)
```

Read-only preparation must prove from the already-loaded `fleets.php` DOM:

- exact `tr.espionageClass` row;
- exact `spy1Link-<fleet_id>` / `processSpy(<fleet_id>)` action;
- source coordinates from that row;
- target coordinates from that row;
- no CAPTCHA;
- already-open `options.php` with rendered `TabAdministrative` reports available for before/after verification.

Only after that preparation succeeds does the coordinator persist a `pending` journal row. Then the backend may invoke `window.processSpy(Number(fleetId))` exactly once.

## Verification

Before the mutation V2 captures the current report-ID set. After the single mutation attempt it refreshes only the already-open `TabAdministrative` content through the game's existing loader; it does not navigate, create tabs, delete messages, or solve CAPTCHA.

A result is `verified` only when V2 observes a report that is:

- new by report/message ID versus the captured baseline;
- exact-target equal to the prepared spy-fleet target;
- timestamped fresh enough for the current request (UTC+04 server wall clock normalized to UTC).

Anything else is `ambiguous`. Ambiguous requests remain unresolved and block automatic retry.

## Schema correction

V2 schema 5 rebuilds `spy_actions` around exact fleet identity. Existing schema-4 journal rows are preserved, but `fleet_id` is stored as `NULL` because it was never recorded. Their old source/target/status/report evidence is kept; V2 never fabricates a fleet ID retroactively.

New unresolved requests are protected by unique partial indexes on both exact `fleet_id` and source+target.

## UI and automation boundary

V2-45 exposes this only as a manual Recon action:

1. user enters an existing spy fleet ID;
2. V2 performs read-only preparation;
3. V2 displays the exact observed source/target;
4. user explicitly confirms;
5. one journaled attempt occurs.

There is no automatic scheduler integration, no bulk `processSpy(0)`, no message deletion, no browser navigation, and no CAPTCHA action in V2-45.

Any actual *dispatch of spy ships* to create new espionage fleets remains unproven by the saved evidence and must be audited separately before it can become a V2 side effect.
