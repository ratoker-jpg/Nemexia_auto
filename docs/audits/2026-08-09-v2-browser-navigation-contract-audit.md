# V2-67 — browser navigation/read ownership contract audit

Date: 2026-08-09

Starting baseline:

- `70cbc13ccde6e0545083341f6c7a5ebbbe70628a`
- PR #103 — schema-9 debris storage maintenance
- exact post-merge push-CI #214 — green

Scope: research/contract only. No V2 browser navigation, page creation, planet switching, `refreshGalaxy`, background loop, Rest Mode loop, or automatic 3×40 traversal is added by this stage.

## Decision

**NO NAVIGATION BOUNDARY**

The repository proves that the accepted legacy galaxy workflow is **not** merely “change the visible URL/system contents”. Its effective `_ensure_galaxy_page` path can first change the game’s selected planet through the real planet-switch surface. At the same time, neither the legacy bound-tab patch nor current V2 CDP readers prove stable account identity or selected-planet identity for an attached page.

The repository also does not contain sufficient server/client evidence to prove that `refreshGalaxy() -> POST ajax_galaxy.php` is neutral with respect to server-side selected-planet/account session context under redirects, manual tab changes, login transitions, or history changes.

Therefore V2-68 must **not** start under the current evidence set. A dry-run navigation intent would imply a navigation ownership contract that has not been proven.

## 1. Effective legacy patch order

`app_entry.py` installs browser patches in this order before importing `app`:

```text
install_bound_tab_fix()
install_ship_retry_fix()
install_raid_verification_fix()
install_background_browser_fix()
import app as app_module
```

This matters because the effective runtime is not raw `browser.py` alone:

- `bound_tab_fix.py` replaces `BrowserWorker.connect` and `_select_nemexia_page`;
- `background_browser_fix.py` later replaces `_ensure_fleets_page` and `_ensure_galaxy_page`;
- the latter continues to call `_select_nemexia_page`, so it inherits the bound-page selector, but its galaxy navigation semantics come from the background patch.

## 2. What `BOUND-NEMEXIA-TAB` actually proves

The legacy bound-tab patch stores one Playwright page object in `_bound_nemexia_page` after explicit Connect.

A bound page remains valid when all of these are true:

1. the page is not closed;
2. `GAME_HOST` remains present in `page.url`;
3. the page object remains among pages of the connected browser.

Initial choice uses focus/visibility and fails on ambiguous multiple active Nemexia tabs.

This is useful tab-object ownership, but it does **not** prove:

- account/player identity;
- selected planet ID/coordinate;
- that a later manual navigation kept the intended account context;
- that a login redirect/history transition kept the intended semantic ownership;
- that the same game-host page is still the exact surface for which a navigation intent was prepared.

There is no account identity token, player identity token, planet identity token, or immutable bound-page token beyond the live Playwright object itself.

## 3. Selected planet is real mutable game context

`browser.py::_current_planet_coord()` explicitly reads the game’s current selected planet from either hidden current-planet coordinates or the `#planetSwitch` UI.

`browser.py::_select_planet()`:

1. reads the current selected planet;
2. searches `#planetsListHolder a` for the requested own planet;
3. extracts that anchor’s real `href`;
4. executes `page.goto(link)`;
5. waits for the planet-switch UI;
6. re-reads the current selected planet and rejects if the game did not switch to the requested coordinate.

The saved real galaxy fixture confirms the surface is not hypothetical. It renders:

```text
Текущая планета: Москва [3:39:11]
```

and own-planet anchors whose routes are of the form:

```text
change_planet.php?id=<planet-id>
```

with multiple distinct own planets listed.

So selected planet is a mutable session/application context, not merely decorative text in the URL.

## 4. Effective legacy galaxy navigation can mutate selected planet

The active `_ensure_galaxy_page_background()` implementation performs:

```text
select bound Nemexia page
→ _select_planet(page, home)
→ if needed page.goto(galaxy.php?galaxy=<g>&solar=<s>)
→ wait for galaxy DOM
→ CAPTCHA check
→ _load_galaxy_system(page, galaxy, solar)
```

The call to `_select_planet(page, home)` happens before the system load every time. If the requested home differs from the game’s current selected planet, the helper follows a `change_planet.php` link.

Therefore the accepted legacy composite cannot be reused or described as a URL-only/system-content-only primitive.

## 5. `refreshGalaxy` is a remote mutation of rendered galaxy state, but session neutrality is unproven

`browser.py::_load_galaxy_system()`:

- writes requested galaxy/system into `#c1` / `#c2`;
- calls the game function `refreshGalaxy()`;
- explicitly waits for a **POST** response whose URL contains `ajax_galaxy.php`;
- accepts success after the requested controls and rendered `#galaxyHolder` settle;
- checks CAPTCHA before and after.

The saved real galaxy page independently confirms that ordinary galaxy UI controls invoke `refreshGalaxy()` for search/breadcrumb navigation.

This proves that `refreshGalaxy` is not a pure local calculation: it performs a remote request and changes rendered galaxy state.

What the repository does **not** prove is the stronger property needed for a V2 navigation boundary: that this remote request cannot change, derive, or depend on server-side selected-planet/account session context in a way that matters to subsequent actions.

No captured request payload/response contract, server implementation, or before/after account-context fixture establishes that guarantee. The saved HTML shows the selected-planet surface, but it is only one state snapshot, not a proof of invariance across navigation.

## 6. Current V2 attach-only readers are deliberately not navigation owners

Current V2 readers remain safer because they do not navigate.

`ReadOnlyCdpBackend._existing_fleets_page()` scans existing open pages and selects a matching game-host `fleets.php` page.

`ReadOnlyAsteroidCdpBackend._existing_galaxy_page()` scans existing open pages and selects a matching game-host `galaxy.php` page.

They do not:

- create a page;
- call `goto`;
- call `refreshGalaxy`;
- switch planets;
- bind a stable page token;
- prove account identity;
- prove selected-planet identity.

That is acceptable for the current read contract because the operator must already have opened the required page and V2 only consumes rendered facts. It is **not** sufficient ownership for V2 to begin changing that page.

## 7. Why URL verification is insufficient

A candidate navigation contract cannot safely say “same host + expected URL means success”.

The evidence shows two separate dimensions:

- route/display state: `galaxy.php?galaxy=<g>&solar=<s>` and rendered `#c1/#c2/#galaxyHolder`;
- selected planet state: `#planetSwitch` and `change_planet.php?id=<planet-id>`.

A page may satisfy the first while the application/session selected planet is a separate value. The legacy code itself recognizes this by explicitly selecting and then verifying the requested home planet before galaxy work.

Current bound-tab validation only checks host/page-object membership. It cannot detect an unintended planet/account context change.

## 8. Ambiguity/recovery cases that remain unowned

The repository does not yet define a fail-closed navigation result for:

- operator manually changes the bound page after a dry-run intent is prepared;
- page redirects to login/bot-check and then back to the game host;
- account/session context changes while the same Playwright page object survives;
- selected planet changes between intent preparation and destination verification;
- multiple matching V2 pages exist and the first-by-URL page is not the intended owned page;
- `refreshGalaxy` receives an accepted response but destination/account facts cannot be proven afterward;
- navigation partially completes and process/window closes before verification.

Without typed ownership and recovery semantics, implementing a write-like browser navigation attempt would create the same class of “remote effect may have happened” ambiguity that V2 journals explicitly avoid for fleet actions.

## 9. V2-67 acceptance decision

The safe result of this audit is not a guessed primitive. It is:

```text
NO NAVIGATION BOUNDARY
```

Under the current repository evidence, V2 may continue to:

- attach to an existing browser;
- read already-open `fleets.php`, `options.php`, and `galaxy.php` surfaces;
- read current selected-planet/account facts when needed for diagnostics/contract research;
- build additional sanitized evidence fixtures.

V2 must **not** yet:

- call `page.goto()` as a navigation feature;
- call `refreshGalaxy()`;
- POST `ajax_galaxy.php` for navigation;
- call/follow `change_planet.php`;
- create tabs;
- automatically traverse 3×40 systems;
- implement Rest Mode page-opening/refresh loops;
- navigate in background.

## 10. What evidence would be required to reopen the boundary

Before V2-68 can be reconsidered, a separate evidence update must prove all of the following, not merely propose them:

1. **Account identity fact** readable before and after navigation from a stable game-owned source.
2. **Selected planet identity fact** readable before and after navigation, including exact planet ID/coordinate semantics.
3. **Stable bound-page ownership** for one explicitly selected existing page, not “first page whose URL matches”.
4. **Exact navigation request contract** for the candidate primitive, including request payload and whether it changes session-selected planet or other account state.
5. **Destination verification contract** that proves page identity, account identity, selected planet identity and requested route/system together.
6. **Redirect/login/CAPTCHA classification** with fail-closed outcomes.
7. **Ambiguous navigation recovery**: no automatic second navigation attempt when the first may have completed but verification was lost.
8. Evidence that manual page/account/planet changes invalidate any prepared navigation intent.

Only after those facts are evidence-backed would a V2-68 typed dry-run intent be meaningful.

## 11. Batch consequence

Per the navigation batch plan, inability to prove the safety contract stops the batch.

Therefore:

- V2-67 may close as a research/audit stage with `NO NAVIGATION BOUNDARY`;
- **V2-68 is not started**;
- V2-69 explicit single-step navigation is not eligible;
- V2-70 navigation recovery/parity is not eligible;
- automatic 3×40 traversal, Rest Mode loops and background navigation remain prohibited.

A future batch may reopen the contract only after new evidence satisfies section 10.

## Verification

V2-67 changes only audit/fixture/test material. The same repository gate still applies:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke;
- no unresolved substantive P1/P2 review findings.
