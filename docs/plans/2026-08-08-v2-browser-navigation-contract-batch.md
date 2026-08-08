# Nemexia Raid Manager V2 — browser navigation/read ownership contract batch

Date: 2026-08-08

Completed action baseline before this plan:

- `1077125a59a96274017ad09c9814431bdaeb614e`
- PR #101 / V2-66 — debris/recycling parity gate
- push-CI run #206 — green on the exact squash SHA

The debris batch intentionally stopped short of the legacy automatic 3×40 scan because V2 is attach-only and has no approved browser-navigation ownership contract.

This next batch exists to answer that architectural gap before Rest Mode, full debris traversal or any other feature can navigate the account.

## Why this batch is required

Two accepted legacy/product concepts currently depend on navigation that V2 explicitly forbids:

1. legacy debris discovery changes galaxy/system while scanning galaxies 1–3, systems 40→1;
2. the existing Rest Mode / attack-watch concept assumes opening or refreshing the Flights page.

Neither behavior may be copied into V2 by adding `goto`, `refreshGalaxy`, tab creation or a background loop inside an unrelated feature.

## Non-negotiable starting boundaries

Until a stage below explicitly proves and gates a narrower primitive, preserve the current baseline:

- attach to an already-running Chromium/Yandex session only;
- do not launch the browser;
- do not create tabs;
- do not navigate automatically;
- do not switch planets/systems automatically;
- do not call legacy `refreshGalaxy`;
- CAPTCHA is detect → STOP only;
- never solve/click/bypass CAPTCHA;
- no automatic retry after ambiguous browser or remote-effect state;
- legacy SQLite stays strictly read-only;
- default launcher stays `run_app.bat -> app_entry.py`;
- no asteroid/debris scheduler is introduced by this batch;
- UI strings never define navigation/business logic.

Automatic 3×40 traversal remains **deferred for the whole batch**. This batch may at most establish a safe explicit single-step navigation primitive after audit proof; loops/full scans require a later separate gate.

# V2-67 — effective navigation contract audit + sanitized fixtures

**Research/contract only. No live navigation.**

Inventory effective legacy and current V2 browser ownership:

- how existing pages/tabs are discovered and selected;
- all effective `goto`, `refreshGalaxy`, galaxy/system switching and Flights-opening paths;
- `_ensure_galaxy_page(...)`, `_load_galaxy_system(...)` and equivalent patched call sites;
- whether a navigation action mutates selected planet/account context or only the displayed route;
- how current server time, CAPTCHA and page readiness are proven before/after navigation;
- what happens when the operator manually changes the tab/page during an operation;
- what evidence is available to prove the destination after navigation;
- whether history/back/redirect/login/CAPTCHA can make destination ambiguous;
- whether navigation can safely remain confined to one already-attached operator-selected tab.

Deliverables:

- `docs/audits/...navigation-contract-audit.md`;
- sanitized page/redirect/CAPTCHA fixtures where repository evidence permits;
- pure typed contract tests;
- explicit decision: `NO NAVIGATION BOUNDARY` or the exact narrow primitive that can be safely implemented.

If destination/ownership/ambiguity semantics cannot be proved, stop the batch here. Do not guess.

# V2-68 — typed bound-tab ownership + navigation intent

Only if V2-67 proves enough evidence.

Add a typed application/domain contract that represents:

- the exact attached CDP endpoint;
- the exact already-existing tab/page identity owned for the operation;
- observed starting URL/page kind;
- requested destination intent;
- expected destination proof;
- CAPTCHA/redirect/unavailable/ownership-lost states;
- cancellation before navigation starts.

This stage remains **dry-run/read-only planning**. It must not call `goto`, click links, create tabs or loop over systems.

Changing tabs/pages manually must invalidate stale prepared navigation intent rather than silently retargeting another page.

# V2-69 — explicit single-step navigation gate, conditional

Implement **only if** V2-67/V2-68 prove a safe ownership and verification model.

Allowed scope is one operator-confirmed navigation step on one already-attached, already-owned tab.

Required properties:

1. typed destination, never a UI-string-driven route;
2. read-only preparation/diff before mutation;
3. explicit operator confirmation;
4. exact bound-tab identity immediately before mutation;
5. CAPTCHA check immediately before mutation;
6. exactly one navigation attempt;
7. exact destination verification after the attempt;
8. redirect/CAPTCHA/tab-loss/unknown outcome becomes ambiguous or stopped;
9. no retry;
10. no second navigation starts automatically.

Still forbidden:

- loops;
- 3×40 traversal;
- background Rest Mode navigation;
- automatic page refresh;
- tab creation/browser launch;
- SendFleet/processSpy/message mutation as part of navigation.

If a safe single-step primitive cannot be proven, V2-69 must be a documented stop/gate rather than an implementation.

# V2-70 — navigation ownership recovery/parity gate + handoff

Cover at minimum:

- restart with no persisted navigation arm;
- tab manually closed;
- tab manually navigated elsewhere;
- duplicate confirmation/click;
- CAPTCHA before navigation;
- CAPTCHA/redirect/unknown destination after the one attempt;
- page load timeout;
- login/session redirect;
- operator cancels before the attempt;
- window/page hide;
- no automatic retry;
- no automatic second step;
- no browser/tab creation;
- no false claim that full debris traversal or Rest Mode is now enabled.

Final gate must state whether a later batch may build a controlled multi-step traversal on top of the proven primitive. It must not implement that traversal itself.

## Explicitly deferred beyond V2-70

- automatic 3×40 debris traversal;
- background/unattended galaxy scanning;
- Rest Mode background page switching/refresh loops;
- asteroid/debris auto-repeat;
- CAPTCHA interaction;
- message deletion;
- default launcher cutover;
- legacy code deletion.

## Per-stage discipline

Each V2 stage is a separate branch and PR.

Before every stage:

1. verify exact `main`;
2. verify previous squash is in `main`;
3. verify push-CI green on that exact SHA;
4. create a fresh branch;
5. reread effective call sites.

After every stage:

1. tests;
2. PR;
3. full CI;
4. review threads/reviews;
5. fix substantive P1/P2 without weakening safety invariants;
6. squash merge;
7. capture exact squash SHA;
8. verify push-CI on that exact SHA;
9. only then start the next stage.

CI remains:

- Windows Python 3.10: compileall + pytest + legacy self-test;
- Windows Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.
