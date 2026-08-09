# UI — Browser Readiness panel

Date: 2026-08-09

Baseline: `ce7bc122f3acfad6b08f2913ed23c00aae03ec6f` (AUTO-06 squash PR #133, post-main CI #322 green).

## Scope

This is a UI-only follow-up to AUTO-06. It does not add or change browser automation, navigation, journals, domain services, persistence, or selectors.

The main Qt shell now surfaces the application `browser_readiness()` contract as six compact states:

```text
Browser
Account
Planet
Fleets
Messages
Galaxy
```

Ready states use the target language `connected / identified / selected / ready`. Not-ready, blocked and stopped states remain visually distinct. CAPTCHA-derived errors render as stopped/danger.

## Non-blocking UI

Readiness is fetched through `QThreadPool` instead of the Qt GUI thread. This prevents an unavailable CDP endpoint from freezing normal window startup or navigation.

The panel refreshes after startup, periodically, when the user changes V2 pages, and by an explicit Refresh button. Overlapping reads are suppressed.

## Boundary

`v2/ui/browser_readiness_panel.py` only calls:

```text
context.browser_readiness()
```

It contains no Playwright/CDP imports, browser selectors, navigation endpoints, fleet actions, or game JavaScript.

The old migration-era `ATTACH-ONLY` shell copy is removed because AUTO-06 now owns recoverable page preparation through NavigationCoordinator. The sidebar instead communicates journaled automation safety.

Full 11→6 information-architecture consolidation and full visual QA remain separate UI-only PRs; this PR only exposes Browser Readiness.