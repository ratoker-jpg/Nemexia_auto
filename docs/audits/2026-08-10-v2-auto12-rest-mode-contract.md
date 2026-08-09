# AUTO-12 — Rest Mode contract / safety audit

Date: 2026-08-10

Baseline:

- exact `main`: `1b4f35773cda354daa7b38f70a94494458562572`;
- AUTO-11 asteroid autorenew + UI follow-up are complete;
- exact post-main CI #398: green.

Scope: **CONTRACT / AUDIT ONLY**. This change must not implement Rest Mode runtime behavior, selectors, timers, notifications, persistence schema, navigation, fleet actions, or UI controls.

Primary inputs:

- `docs/plans/2026-08-06-rest-mode-and-attack-watch.md`;
- `docs/plans/2026-08-09-v2-full-automation-ui-consolidation.md`;
- `docs/audits/2026-08-09-v2-auto01-effective-legacy-automation-parity.md`;
- real saved `fleets.php`: `saved_pages/2026-08-08_08-54-11-072/page.html`;
- current V2 BrowserIdentity / BrowserReadiness / NavigationCoordinator / AutomationAuthority contracts.

## Decision

AUTO-12 is an approved **new V2 feature**, not recovered legacy parity.

The effective legacy runtime has no Rest Mode implementation. The older Rest Mode document is explicitly a future product contract. AUTO-14 must therefore never claim that AUTO-12 recovered a legacy feature that did not exist.

The first implementable Rest Mode is an **observation-only activity watcher**. It may prepare/read the verified `fleets.php` surface, observe the activity-check timer, detect CAPTCHA/anti-bot state, persist typed state/recovery evidence, and notify the operator. It must not send fleets, change raid queues, defend automatically, solve CAPTCHA, click `Continue`, or invent an incoming-attack parser from unverified DOM.

## Evidence confirmed from the saved game page

The saved `fleets.php` page proves these game-owned facts:

```text
<title>... // Полеты</title>
StringServerTime = 'Время сервера (UTC+04:00)'
StringBotcheckTime = 'Автоматический режим проверки через %1$s мин.'
BOT_CHECK = ...
BOTCHECK_ACTIVE = true
BOTCHECK_PAGE_LOCK = false
URL_REDIRECT = 'bot_check.php?redir=%2Ffleets.php'
currentTime = new Date(...)
```

This is enough to authorize a read-only activity-timer adapter in the implementation stage, provided its parser is fixture-tested against saved-page evidence.

It does **not** prove the exact DOM of a real incoming attack. The approved 2026-08-06 contract already requires a saved page captured during a real attack before exact attack selectors/row semantics are implemented.

## Frozen AUTO-12 state model

Persist one typed Rest Mode state. Recommended terminal/runtime values:

```text
DISARMED
STARTING
WATCHING
ACTIVITY_WARNING
BLOCKED_BROWSER
BLOCKED_IDENTITY
BLOCKED_BUSY
BLOCKED_AMBIGUOUS
CAPTCHA_REQUIRED
ERROR
```

Rules:

- process startup is always `DISARMED`;
- persisted evidence from a previous run is loaded for diagnosis, but must never auto-arm;
- `Start` is the only transition from a safe disarmed/blocked state into `STARTING`;
- `Stop` is explicit and always available while the mode is armed;
- CAPTCHA immediately disarms and persists `CAPTCHA_REQUIRED`;
- browser/tab/session loss immediately disarms and persists `BLOCKED_BROWSER`;
- account/planet proof loss immediately disarms and persists `BLOCKED_IDENTITY`;
- an unresolved/ambiguous NavigationCoordinator effect immediately disarms and persists `BLOCKED_AMBIGUOUS`; no automatic retry is allowed;
- unexpected read/parser errors fail closed to `ERROR` and never become a successful “no warning” result.

`WATCHING` and `ACTIVITY_WARNING` are the only normally armed states.

## Explicit Start / Stop contract

### Start

`Start Rest Mode` must perform, in order:

1. prove no unresolved NavigationCoordinator journal entry blocks new context work;
2. acquire the Rest Mode process-level automation/browser authority;
3. obtain Browser Readiness;
4. prove one live Nemexia session, `AccountContext`, and selected `PlanetIdentity`;
5. persist the exact server host, account ownership fingerprint, planet ID and coordinate used as the session identity anchor;
6. prepare `fleets.php` only through BrowserReadiness / NavigationCoordinator;
7. verify the same account + selected planet after preparation;
8. run one read-only observation;
9. enter `WATCHING` only after the observation is complete and CAPTCHA-free.

Any failure before a verified working state leaves the mode disarmed and persists the reason.

### Stop

`Stop Rest Mode` must:

- set `armed = false` persistently before any further scheduled cycle;
- cancel/ignore future local timer ticks;
- release the Rest Mode authority token;
- perform **no browser mutation** merely to stop;
- retain last successful observation, warning state and recovery/error evidence.

Closing the application has the same fail-safe arming outcome: next startup is disarmed.

## AccountContext / PlanetIdentity invariant

Every successful cycle is bound to the identity captured on Start:

```text
server_host
account.ownership_fingerprint
selected planet_id
selected planet.coord
```

Before and after any NavigationCoordinator page preparation, all four must still match.

A manual planet/account change is not silently accepted as a new Rest Mode identity. The mode stops/blocks and requires an explicit new Start after the operator chooses the intended context.

The first attack parser, when evidence eventually exists, may report attacks targeting any proven owned `PlanetIdentity`; it must not weaken the selected-planet identity used to prove safe browser ownership.

## Navigation ownership

Rest Mode never calls Playwright/CDP navigation or browser selectors from application/UI code.

Allowed preparation path:

```text
RestModeService
→ BrowserReadinessManager / typed application context
→ NavigationCoordinator
→ journaled verified fleets.php preparation
```

A Rest Mode read adapter may inspect the **already coordinator-owned page** read-only. It may not own a second browser/page chooser and may not silently rebind to another Nemexia tab.

If a page preparation is `AMBIGUOUS`, Rest Mode persists `BLOCKED_AMBIGUOUS`, disarms, and performs zero new automatic navigation attempts until the uncertainty is reconciled or the operator explicitly recovers through a safe path.

## Browser Readiness / session loss

A cycle must stop rather than degrade to empty data when any of these becomes unproven:

- browser/CDP connection;
- bound Nemexia page;
- game server host;
- account ownership fingerprint;
- selected `PlanetIdentity`;
- `fleets.php` readiness required for that observation.

Browser closed, tab closed, login redirect, ambiguous game tab or session loss therefore become `BLOCKED_BROWSER` or `BLOCKED_IDENTITY` with `armed = false`.

No “empty flights” or missing DOM result may be interpreted as “everything is safe”.

## CAPTCHA boundary

CAPTCHA is a global STOP condition.

Detection evidence includes the already-established V2/legacy signals such as reCAPTCHA presence, known anti-bot text, `BOTCHECK_PAGE_LOCK`, or a verified bot-check page/redirect.

On detection:

1. persist `CAPTCHA_REQUIRED`;
2. set `armed = false`;
3. release Rest Mode authority;
4. suppress all further Rest Mode navigation/read cycles;
5. notify the operator.

Forbidden:

- clicking reCAPTCHA;
- solving it;
- emulating a human;
- clicking `Continue` automatically;
- retrying through the protection page.

After manual completion, the operator must use explicit Start again. Merely observing that CAPTCHA disappeared must not auto-resume Rest Mode.

## Activity-watch semantics

Default interval: **5 minutes**.

First-version warning threshold: **25 minutes**.

One cycle:

```text
check armed state
→ prove authority + no unresolved navigation
→ Browser Readiness
→ prove AccountContext / PlanetIdentity
→ ensure fleets.php through NavigationCoordinator if needed
→ prove identity again
→ read CAPTCHA + activity timer from the owned page
→ persist complete observation
→ emit at most one threshold warning
→ schedule next local cycle
```

The activity timer reader must be read-only and fixture-tested. It must never fabricate a value when the expected game-owned evidence is absent or malformed.

25-minute warning dedupe:

- notify only on the transition from a confirmed value `> 25` to a confirmed value `<= 25` within the same activity-check epoch;
- do not notify every 5-minute cycle while remaining below the threshold;
- if the timer later increases enough to prove a new activity-check epoch, the threshold may arm again;
- missing/unreadable timer data is an error/blocked observation, not “no warning”.

## Attack-watch semantics

Attack-watch behavior is frozen now even though the exact parser is **not authorized yet**.

Preferred attack identity remains:

```text
fleet_id
```

Fallback only when proven by a real saved attack page:

```text
target_coord + arrival_at + mission + source
```

Notification rules once a verified parser exists:

- notify on a newly observed attack identity;
- notify when the confirmed incoming-attack count increases;
- do not re-notify the same unchanged attack every 5 minutes;
- a decrease alone does not require an alarm;
- persist dedupe state across restart for still-active attacks;
- target coordinates must map to the proven owned-planet set when detailed target evidence is available.

### Current evidence gate

There is currently no repository fixture proving the DOM of a **real incoming attack**. Therefore the initial AUTO-12 implementation must expose attack-watch state as something equivalent to:

```text
UNVERIFIED_DATA_REQUIRED
```

until a real attack snapshot is supplied and audited.

It is forbidden to:

- guess selectors;
- treat an unrecognized/absent attack DOM as `0 attacks`;
- repurpose ordinary outbound/returning flight rows as proof of incoming attacks;
- claim incoming-attack monitoring is implemented merely because `fleets.php` can be read.

This limitation is explicit product truth, not a silent fallback.

## Persistent typed state / recovery evidence

Implementation must use a V2-owned component-versioned schema and typed repository. Minimum persisted fields:

```text
armed
status
session_id
server_host
account_fingerprint
planet_id
planet_coord
started_at
last_success_at
next_check_at
last_activity_minutes
activity_warning_epoch / dedupe evidence
attack_watch_state
last_attack_snapshot metadata when verified evidence exists
last_error
blocking_navigation_request_id when applicable
updated_at
```

Crash/restart rule:

- persisted `armed = true` from a prior process is never trusted as permission to resume;
- startup rewrites runtime authority to disarmed/recovery state while preserving the prior session/evidence for diagnosis;
- unresolved NavigationCoordinator/action evidence is never erased by Rest Mode recovery.

## Mutual exclusion

Rest Mode does **not** initiate fleet sends in the approved first version. Nevertheless it controls the same bound browser/page and performs coordinator navigation, so concurrent automatic workflows would create context races.

Therefore AUTO-12 must extend the existing process-level `AutomationAuthority` with a Rest Mode owner and hold that authority for the whole armed session.

While Rest Mode is armed:

- AutoFarm cannot arm;
- asteroid autorenew cannot arm;
- Rest Mode cannot arm if either already owns authority;
- manual bounded operations that can drive the same browser must either be explicitly blocked by UI/application entry gates or require Rest Mode to be stopped first.

This is a browser/context exclusion rule, not authorization for Rest Mode to send anything.

If a future Rest Mode revision ever gains a remote action, that action requires its own immutable request/journal and exactly-one attempt semantics; no such action is authorized by AUTO-12 v1.

## Notification boundary

Notifications are local operator signals only.

Required events for the first implementation:

- activity timer crosses the 25-minute threshold;
- CAPTCHA stop;
- browser/session/identity loss that stops the mode;
- persistent ERROR/BLOCKED condition where operator action is required.

Windows toast/sound is presentation/infrastructure. Failure to deliver a toast must not alter the browser safety state or trigger a remote retry.

Attack notifications are enabled only after the attack parser evidence gate is satisfied.

## Implementation split after this audit

To preserve the project rule that business/browser work and UI-only work do not mix:

### AUTO-12A — runtime implementation PR

May add:

- typed Rest Mode state/service;
- component-versioned V2 persistence;
- coordinator-owned read-only activity/CAPTCHA adapter;
- 5-minute runtime driver;
- Rest Mode automation authority owner/interlocks;
- typed application-context methods;
- tests and implementation audit update.

Must not add Rest Mode UI controls in the same PR.

### AUTO-12B — UI-only follow-up PR

After AUTO-12A squash + exact post-main green:

- explicit Start / Stop;
- current state;
- last/next check;
- activity minutes / 25-minute warning;
- verified account/planet identity;
- attack-watch state (`UNVERIFIED_DATA_REQUIRED` until evidence exists);
- last result/error;
- typed context only.

No selectors, CDP, scheduler implementation, persistence schema, or fleet-action logic in the UI PR.

## Acceptance gate before AUTO-13

AUTO-12 is fully green only when:

- this contract/audit PR is merged and exact post-main CI is green;
- AUTO-12A runtime PR is merged and exact post-main CI is green;
- AUTO-12B UI-only PR is merged and exact post-main CI is green;
- startup is proven disarmed;
- explicit Start/Stop are proven;
- AccountContext / PlanetIdentity are revalidated;
- NavigationCoordinator is the sole context mutation owner;
- Browser Readiness participates in every start/cycle requiring page preparation;
- CAPTCHA stops and cannot auto-resume;
- browser/session loss stops/blocks;
- ambiguity causes zero blind retries;
- typed recovery evidence survives restart;
- Rest Mode is mutually exclusive with competing automatic browser senders;
- attack-watch capability truthfully reports the evidence gate and never false-zeroes attacks.

AUTO-13 and AUTO-14 remain forbidden until every applicable AUTO-12 gate above is green.
