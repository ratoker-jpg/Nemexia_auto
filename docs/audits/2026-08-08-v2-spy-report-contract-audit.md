# V2-41 — spy/report contract audit

Date: 2026-08-08

Baseline: `8e776c0f72bbaa6ff772d090e06c791a9e88c436` (`main`, docs handoff #72).

Scope: research/contract only. This change must not request spies, delete messages, navigate the browser, mutate legacy SQLite, or add a new game-side effect.

## Effective legacy runtime

The default launcher remains `run_app.bat -> app_entry.py`. The effective Tkinter runtime is not only `app.py`: `app_entry.py` installs patch modules in order. The reconnaissance contracts relevant to this audit are therefore the patched runtime behavior:

1. `install_report_time_freshness_fix(BaseRaidManagerApp)`;
2. `install_resource_queue_modes(BaseRaidManagerApp)`;
3. `install_resource_farm_auto(BaseRaidManagerApp)`;
4. `install_farm_no_target_retry(BaseRaidManagerApp)`.

V2 must preserve the accepted behavior of that effective stack, not copy stale pre-patch assumptions from individual base functions.

## Message/report read contract

Nemexia messages are hosted inside `options.php`, not a standalone `messages.php` page.

Legacy read path:

- game page: `https://game.ares.nemexia.com/options.php`;
- spy/system tab: `TabAdministrative`, message type `2`;
- battle reports tab: `TabReports`, message type `3`;
- game loader: `loadTabContent(tabId, messageType, pageIndex)`;
- loader endpoint confirmed by the legacy audit: `ajax_messages.php`, `option=viewMessages`;
- tab HTML source: `#<tabId>Box`;
- message list: `#messagesList > .messageItem`;
- timestamp: `.messageDate`;
- body: `.messageBody`, normally `id="body-<message_id>"`;
- fallback message identity: `input[name^='messageSelect']` value;
- target coordinates: link query facts `c1`, `c2`, `c3` or the visible coordinate text;
- pagination: `loadTabContent(..., pageIndex)` indices and the game's `typeHandler` cache.

`BrowserWorker.collect_spy_reports()` reads `TabAdministrative`, type `2`, through the game's own loader and parses the resulting HTML with `parse_spy_reports_html()`.

The legacy reader is allowed to navigate to `options.php` and may create/select pages through `BrowserWorker`. That navigation behavior is **not** part of the V2 contract. Current V2 browser access remains attach-only and V2-42 must fail unavailable when the required already-open page is absent rather than silently navigating.

## Spy report acquisition side effect

### V2-45 correction to the original V2-41 interpretation

The original V2-41 wording called `processSpy(0)` a mass "spy request" and V2-43/44 initially modeled a new request as `source + target + probe_count`. Later inspection of the preserved real `fleets.php` page proved that model was too broad and must not be carried into the first live mutation.

The saved page shows two distinct controls:

- each existing espionage fleet row has an exact action such as `processSpy(152272)` and a matching `spy1Link-152272`;
- the bulk control calls `processSpy('0', true)` and is visibly labeled **"Получить все шпионские отчеты"**.

Therefore `processSpy` processes/retrieves a report for an **already existing espionage fleet**. It is not evidence of a command that dispatches new probes to an arbitrary source/target pair. The exact one-shot V2 identity is consequently:

```text
existing espionage fleet_id + source + target observed from that exact fleets.php row
```

`source` and `target` are preparation facts derived from the live row, not caller-selected routing inputs. V2-45 must call only `processSpy(exact_fleet_id)` once. It must not use the bulk `processSpy(0)` path.

The prior browser audit still correctly identified the remote endpoint family: `ajax_fleets.php`, `type=processSpy`, with the selected fleet identity carried as `fleet_id`. The exact success response contract is not sufficiently proven by saved-page evidence, so V2 must verify success from a newly observed report/message identity with the exact target and fresh timestamp rather than trusting the JavaScript call return value.

Current legacy `BrowserWorker.request_all_spy_reports()` still executes the bulk `processSpy(0)` behavior. That legacy implementation remains untouched. V2-45 deliberately uses the safer exact-fleet action instead.

## Legacy message deletion

The legacy clean-refresh/AutoFarm path can delete recognized spy messages before requesting new reconnaissance. The selected-message call posts to `ajax_messages.php` with:

- `option=deleteSelectedMessages`;
- `type=2`;
- comma-separated message IDs.

The AutoFarm implementation excludes protected coordinates from that deletion set.

This behavior is deliberately **not migrated** in the V2 fresh-recon batch. V2-41 adds no deletion contract, and V2-42 through V2-50 must not make message deletion automatic.

## Report identity and available facts

The current parser can expose these report facts from a recognized spy message:

- message/report ID when available;
- exact target coordinates;
- report timestamp;
- energy;
- metal;
- minerals;
- gas;
- population;
- ships;
- defense;
- completeness marker/raw payload in the legacy model.

For future mutation verification, the minimum useful typed identity is:

```text
report_id + exact target + normalized report timestamp
```

Resource facts are report snapshots, not claims about the target's current live balance.

A missing timestamp must not be replaced with the current time. An undated report is not fresh evidence.

## Timestamp/freshness contract

Nemexia report timestamps are server wall-clock values interpreted by the effective runtime as UTC+04:00 and normalized to UTC before freshness comparisons.

The base `reports.py` parser historically labels the parsed wall-clock as UTC; `report_time_freshness_fix.py` corrects this in the effective runtime. V2 must preserve the corrected interpretation, not the historical parser bug.

The accepted default freshness window is `report_lookback_hours = 24` hours. A report is fresh when its normalized timestamp is at or after `now - lookback`.

## Eligibility contracts

These are distinct policies and must not be collapsed into one threshold.

### Manual metal queue

After target-level filters (enabled, not blacklisted, not active, has a spy timestamp), the report must contain metal at or above the configured minimum. Effective default:

```text
metal >= 480,000
```

Ranking: metal descending, then coordinates.

### Manual mineral queue

After the same target-level filters, minerals only need to be reported (`minerals is not None`). There is no 500k threshold in this manual queue mode.

Ranking: minerals descending, then coordinates.

### Legacy AutoFarm 500k

After target-level filters, AutoFarm requires:

```text
minerals >= 500,000
```

Ranking: minerals descending, metal descending, then coordinates.

## Recon-cycle outcome contract

The next V2 stages must keep the following states separate:

| State | Meaning | Required behavior |
| --- | --- | --- |
| `no_fresh_reports` | A requested/read reconnaissance cycle produced no fresh report evidence at all | stop/fail closed; **not** the 25-minute empty-result cooldown |
| `fresh_zero_eligible` | Fresh report evidence exists, but eligibility policy returns zero targets | successful empty scan; apply the fixed 25-minute no-target cooldown |
| `captcha` | CAPTCHA/bot check is present | stop/fail closed; user handles it manually; never solve/click/bypass |
| `live_unavailable` | Required browser/CDP/page/read facts are unavailable | stop/fail closed; do not infer a successful empty scan |
| `ready` | Fresh report evidence exists and at least one eligible target exists | safe input for later ingestion/refill policy |

The effective legacy patch fixes the successful-empty-scan cooldown at exactly **25 minutes**. It is independent of the attack return buffer and must not be reused for `no_fresh_reports`, CAPTCHA, or browser failures.

## CAPTCHA contract

Legacy and V2 live code recognize CAPTCHA/bot-lock evidence from the page, including reCAPTCHA markup, `BOTCHECK_PAGE_LOCK`, and human-verification phrases. The migration contract is unchanged:

- detect;
- stop/report;
- require manual user action;
- never solve, click, or bypass.

## V2-41 typed contract and fixtures

V2-41 adds a pure `v2.domain.recon` contract with:

- normalized `SpyReportFact`;
- explicit recon outcome enum;
- UTC+04 server-time normalization;
- 24-hour default freshness rule;
- separate manual metal/manual mineral/AutoFarm eligibility predicates;
- fixed 25-minute successful-empty-scan constant.

A sanitized HTML fixture locks the report-ID/target/timestamp/resource parsing facts without containing account-specific data.

No V2 browser backend, UI action, scheduler, SQLite schema, or game-side mutation was added in V2-41.

## Constraints for the next stages

V2-42 may add only an attach-only report source/freshness reader. It must not call `processSpy`, delete messages, create tabs, or navigate to `options.php` automatically.

Before V2-45 performs the first real spy-report acquisition, the mutation path must already have:

1. typed exact-fleet command and validation;
2. source/target derived from the exact live espionage row;
3. explicit action gate;
4. persistent immutable request identity;
5. idempotency/unresolved-request blocking;
6. exactly one `processSpy(exact_fleet_id)` mutation attempt;
7. verification from a newly observed exact report/message identity + target + fresh timestamp;
8. conservative ambiguous handling and no automatic retry.
