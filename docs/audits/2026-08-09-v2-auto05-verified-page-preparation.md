# AUTO-05 — verified fleets / System messages / galaxy preparation

Date: 2026-08-09

Baseline: `b19b92bf933dff15cebd7bdd3673e31c41a145ac` (AUTO-04 squash PR #131, push CI #304 green).

## Scope

AUTO-05 makes the central NavigationCoordinator capable of preparing the three game surfaces required by the next automation stages:

- `fleets.php`;
- `options.php` + rendered System messages;
- `galaxy.php`.

The coordinator still owns one exact runtime Nemexia `Page`. Feature services and Qt do not import Playwright/CDP selectors.

## Initial page ownership

AUTO-03 originally required the operator to pre-open `fleets.php` before the coordinator could bind. AUTO-05 removes that unnecessary path requirement.

The coordinator may now bind exactly one already-open page on the configured Nemexia game host. Zero matching game pages or multiple matching game pages fail closed. The same exact runtime `Page` object remains owned after later page preparation.

This stage does **not** yet launch Yandex, create a new Nemexia page, resolve multiple game tabs automatically or recover a lost page. Those belong to Browser Readiness / recovery stages.

## Readiness evidence

Every navigation observation now records typed page evidence:

```text
page_kind
fleets_ready
options_ready
messages_ready
galaxy_ready
galaxy
solar
```

Proven anchors are based on the supplied browser reference and effective legacy runtime:

```text
fleets.php
#FleetsCount
#MaxFleets

options.php
#messagesFolders
#TabAdministrative / #TabAdministrativeBox
#messagesList / rendered System-message evidence

galaxy.php
#galaxyHolder
#c1
#c2
```

Account fingerprint and selected `PlanetIdentity` are re-read before and after page preparation.

## Exactly-one page navigation

`prepare_fleets` and `prepare_galaxy` each use one immutable journal request.

For one request:

1. observe bound page + account + selected planet + page state;
2. persist before/intent;
3. if already ready, finish `verified` with zero remote navigation;
4. otherwise validate account + selected planet again immediately before effect;
5. issue exactly one `page.goto(...)` through the shared navigation helper;
6. verify the same page token, account fingerprint, selected planet and requested page readiness;
7. pre-attempt failure => `failed_safe`;
8. post-attempt uncertainty => read-only reconciliation or `ambiguous`, never automatic retry.

## System messages are two effects, not one hidden macro

Preparing System messages requires two distinct browser effects:

1. prepare `options.php`;
2. invoke the proven game route `loadTabContent('TabAdministrative', 2, 0)` (with local `showTab` when available) and wait for rendered System-message evidence.

AUTO-05 journals these separately:

```text
<request_id>             phase=options_page
<request_id>:system-tab  phase=system_tab
```

This prevents a single request ID from concealing two remote effects. If the options page is already ready, the first journal record is verified with zero navigation. If System messages are already rendered, the second record is verified with zero content reload.

## Explicit checkpoint — manual work still required after AUTO-05

AUTO-05 provides the safe primitives, but it does not yet wire a full readiness/orchestration loop into the normal Qt workflow. Therefore the user still has to do the following manually at this checkpoint:

1. **Start/keep a CDP-capable browser available.** V2 still does not launch Yandex or create the first game tab itself.
2. **Keep exactly one authenticated Nemexia game tab available for initial binding.** Zero tabs and multiple matching game tabs fail closed.
3. **Choose the intended planet through the current UX when a workflow has not yet been wired to `PlanetIdentity` selection.** AUTO-04 can switch safely, but the final Qt planet selector/readiness orchestration is not yet connected.
4. **Enter/select an exact processable spy fleet ID for the current recon action.** Automatic exact-fleet discovery is AUTO-07.
5. **Select the required galaxy/system coordinates inside galaxy.php.** AUTO-05 can prepare `galaxy.php`, but it does not call `refreshGalaxy`; system navigation is AUTO-09.
6. **Run 3×40 asteroid/debris discovery manually.** Controlled traversal is AUTO-10.
7. **Restart asteroid cycles manually.** Persisted unattended asteroid autorenew parity is AUTO-11; debris repeat is intentionally not a legacy requirement.
8. **Use no Rest Mode yet.** AUTO-12 is a new approved product contract, not recovered legacy runtime.
9. **Recover lost browser/page context manually.** Automatic context/restart reconciliation is AUTO-13.

The operator no longer needs a dedicated `fleets.php` tab merely to establish coordinator ownership, and the V2 architecture now has verified primitives capable of preparing fleets/System messages/galaxy. The next step is AUTO-06: turn those primitives into human-readable Browser Readiness and invoke them automatically when a workflow needs them.

## Safety boundary after AUTO-05

Still prohibited:

- `refreshGalaxy` / `ajax_galaxy.php` system mutation;
- automatic spy fleet selection/processing orchestration;
- new espionage route creation without proof;
- fleet mutation changes outside existing exactly-one action services;
- CAPTCHA solve/click/bypass;
- automatic retry after ambiguous navigation/content effect;
- UI-level Playwright/CDP selectors.
