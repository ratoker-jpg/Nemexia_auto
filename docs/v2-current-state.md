# Nemexia Raid Manager V2 — current state

Updated by V2-40 after the #62–#71 action-migration batch.

## Safety baseline

The pre-PySide6 working version remains recoverable at:

- `stable/tkinter-v1`
- `archive/pre-pyside6-4e01bfda`
- source SHA `4e01bfda752c6383e48c0f6eb8be64d68676da67`

The default launcher is still `run_app.bat -> app_entry.py` (Tkinter). V2 remains a separate `app_qt.py` entrypoint.

## Storage boundary

Legacy SQLite remains read-only:

- SQLite `mode=ro`;
- `PRAGMA query_only=ON`;
- legacy targets/history/recon and migration inputs are reads only.

V2-owned storage lives under `%LOCALAPPDATA%/NemexiaRaidManagerV2/` and now uses schema version 3:

- typed allow-listed settings;
- `raid_actions` action journal;
- `raid_queue` mutable V2-owned queue;
- atomic settings writes;
- SQLite-native consistent backups with retention.

The legacy Plan is imported into `raid_queue` only when the V2 queue is empty. Once V2 owns the queue, later legacy reads never overwrite its states.

## Live browser boundary

V2 attaches to an existing Chromium/Yandex CDP session and requires an already-open `fleets.php` page. It does not launch the browser, create tabs, or navigate the account.

Read facts include:

- active fleet rows and fleet IDs;
- `#FleetsCount` / `#MaxFleets`;
- own planet coordinates.

CAPTCHA remains fail-closed. V2 does not solve, click, or bypass CAPTCHA.

## Raid action boundary

Mutating raid actions are disabled by default. `actions_enabled` must be explicitly enabled in V2 Settings.

The raid path is now:

1. typed `RaidCommand` validation;
2. attach-only preparation of the existing fleet form;
3. exact source/target/ship-count checks;
4. persistent `request_id` journal entry before SendFleet;
5. exactly one SendFleet attempt;
6. server-response handling;
7. verification against a new exact target + mission `Атака` + fleet ID;
8. `verified` or `ambiguous` journal state;
9. no automatic retry after an ambiguous side effect.

The Plan page provides explicit manual Prepare and Send actions. Send requires a modal confirmation with source, target, player, and ship count.

Disabled and blacklisted targets cannot reach the dispatch backend. A queue row moves to non-retryable `sending` before SendFleet, closing the crash gap where a successful send could otherwise be repeated after restart.

## Reconciliation

Pending/ambiguous raid actions may be reconciled only from an explicit live fleet refresh.

A request becomes verified only when there is one unique matching live attack with:

- exact source;
- exact target;
- mission `Атака`;
- non-empty fleet ID;
- flight time not older than the journal request.

Multiple possible matches remain unresolved. Reconciliation never sends or clicks anything.

## AutoFarm V2

AutoFarm is now built on typed states rather than status-text parsing:

- `actions_disabled`;
- `live_not_checked`;
- `live_unavailable`;
- `blocked_unresolved`;
- `waiting_return`;
- `waiting_capacity`;
- `no_targets`;
- `ready`.

Eligible targets are only V2 queue rows that are:

- `queued`;
- enabled;
- not blacklisted.

A wave is capped by current live free fleet slots, eligible queue size, and the user max-target limit. Every target uses the same persistent journal/idempotency boundary as manual sending. The wave stops at the first error or ambiguous result.

The AutoFarm page supports:

- explicit one-wave execution;
- an explicitly armed continuous in-session cycle;
- 30-second live refresh/capacity checks;
- waiting for farm-blocking attacks;
- configured return buffer;
- return-buffer recovery from verified `farm-*` V2 action-journal timestamps after restart;
- automatic safety-disarm on unresolved action, live failure, or wave error.

Continuous AutoFarm is never persisted as armed. Every new `app_qt.py` process starts with the scheduler off and requires a fresh manual Start confirmation.

V2-40 does **not** automatically request new spy reports or rebuild/refill the queue. When eligible queue targets are exhausted, the scheduler stops.

## Real Qt pages

Backed by real application services/data:

- Overview;
- Plan — V2-owned queue + explicit manual raid actions;
- Active — live flights, typed classification, capacity, journal reconciliation;
- AutoFarm — typed state, one-wave action, controlled in-session cycle;
- Recon — read-only saved spy reports;
- Targets;
- History;
- Settings — V2-owned settings;
- Diagnostics.

Still not migrated as V2 action surfaces:

- Asteroids;
- Debris.

## Explicitly not enabled yet

V2 still has no automatic action API for:

- spy requests / fresh-report acquisition;
- message deletion;
- automatic queue generation/refill from newly scanned reports;
- automatic browser navigation;
- asteroid execution;
- debris/recycling execution;
- CAPTCHA solving.

Because automatic spying/refill is not migrated, the current V2 continuous farm cycle operates only on its existing V2 queue.

## Verification gate

GitHub Actions runs on Windows:

- Python 3.10: compileall + pytest + legacy self-test;
- Python 3.11: compileall + pytest + legacy self-test;
- Python 3.11 + PySide6: real offscreen `QApplication` / `MainWindow` smoke.

CI uses per-ref concurrency so stale superseded branch runs are cancelled instead of delaying the newest head.

The local legacy working installation should not be replaced until final parity/cutover is explicitly completed.
