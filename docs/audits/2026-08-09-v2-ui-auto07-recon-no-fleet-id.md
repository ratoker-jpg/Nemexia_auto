# UI follow-up — AUTO-07 reconnaissance without manual fleet ID

Date: 2026-08-09

Baseline: `56a65d31147d156ec02424e3435de92adfa29d98` (AUTO-07 squash PR #136, exact post-main CI #334 green).

## Scope

This is a UI-only follow-up to AUTO-07. It changes no browser, application, persistence, domain, journal, mutation, or recovery behavior.

The normal Recon surface no longer asks the operator to type an exact Spy fleet ID.

Instead it exposes two application-level commands:

```text
Получить свежий отчёт
Авторазведка → AutoFarm refill
```

They call the already-merged AUTO-07 services:

```text
context.run_automatic_recon(request_id=...)
context.run_automatic_recon_refill(request_id=..., queue_size=45)
```

## User contract

The Qt surface explains that V2:

- prepares the required Fleets/System messages state through the application architecture;
- finds one proven-ready existing spy fleet from live evidence;
- permits at most one journaled remote mutation attempt;
- stops on CAPTCHA;
- never automatically retries an ambiguous remote result;
- does not create a new espionage route in this step.

The separate `Принять уже доступные отчёты` command remains for reports that are already rendered and need V2 ingestion only.

## Removed migration-era UX

The Recon page no longer contains:

- `QLineEdit` for fleet ID;
- `SpyFleetId`;
- `EXACT SPY FLEET ID`;
- manual `prepare_spy` / `process_spy` UI flow;
- direct call to `run_controlled_recon_refill` with a user-supplied fleet ID.

The underlying manual compatibility services remain in the application layer. This UI PR does not delete them because UI consolidation must not remove domain/application capabilities merely because the normal surface no longer exposes them.

## Safety boundary

`v2/ui/pages/recon.py` contains no Playwright/CDP imports, browser selectors, game JavaScript, SQLite access, `processSpy`, page navigation, or CAPTCHA interaction.

All browser ownership, exact-fleet discovery, journaling, exactly-one mutation and verification remain behind AUTO-07 application/infrastructure boundaries.

## Next

After this UI-only PR is squash-merged and exact post-main CI is green, proceed to AUTO-08 as audit-first. Effective legacy evidence currently proves processing existing spy fleets but does not prove creation of a new mission-2 espionage route, so AUTO-08 must not invent that mutation contract.
