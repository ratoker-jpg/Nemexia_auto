# V2-45 — correction to the spy acquisition contract

Date: 2026-08-08

Baseline entering V2-45: `e02418348beb1ee9240b0c30fa7afaaf92cc0dbd`.

## Correction

V2-41 correctly identified legacy `processSpy(0)`, but its interpretation as a target/probe request was not proven. V2-43/44 therefore established the safety boundary before any real mutation, but modeled `source + target + probe_count`.

Re-inspection of saved `fleets.php` proves the real actionable identity:

- an existing fleet exposes exact link `id="spy1Link-152272"` with `onclick="processSpy(152272)"`;
- that row contains source `3:39:11` and target `2:22:19`;
- the raw snapshot also contains `tr.espionageClass`, but V2 does **not** depend on that class or row visibility;
- a separate bulk control calls `processSpy('0', true)` and is labeled `Получить все шпионские отчеты`.

The side effect is therefore **processing an already-existing espionage fleet by fleet ID**. It is not evidence of dispatching arbitrary probe ships to a caller-supplied target. V2 must not invent probe counts, ship keys, or dispatch APIs.

## V2-45 contract

```text
SpyRequestCommand(fleet_id)
```

Read-only preparation must prove from already-loaded pages:

- exact `spy1Link-<fleet_id>` / exact `processSpy(<fleet_id>)` action;
- containing row via `link.closest('tr')`;
- source and target coordinates from that same row;
- no CAPTCHA;
- already-open `options.php` with rendered `TabAdministrative` reports available for verification.

No localized UI text such as `Шпионаж` controls the action boundary.

Only after preparation succeeds does the coordinator persist `pending`. Then the backend may invoke `window.processSpy(Number(fleetId))` exactly once.

## Verification

Before mutation V2 captures currently rendered report IDs. After the single attempt it refreshes only the already-open `TabAdministrative` DOM through the game's loader; it does not navigate, create tabs, delete messages, or solve CAPTCHA.

`verified` requires a report that is:

- new by report/message ID versus baseline;
- exact-target equal to the prepared fleet target;
- fresh by normalized server timestamp.

Anything else is `ambiguous`; automatic retry remains blocked.

## Schema correction

Schema 5 rebuilds `spy_actions` around exact fleet identity. Schema-4 rows are preserved with `fleet_id=NULL`; V2 never fabricates a historical fleet ID. New unresolved requests are protected by unique partial indexes on exact `fleet_id` and source+target.

## UI and automation boundary

V2-45 is manual only: enter fleet ID → read-only preparation → exact observed route shown → explicit confirmation → one journaled attempt.

There is no scheduler integration, bulk `processSpy(0)`, message deletion, browser navigation, CAPTCHA action, or retry. Actual dispatch of spy ships remains unproven and out of scope.
