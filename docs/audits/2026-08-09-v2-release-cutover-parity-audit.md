# Nemexia Raid Manager V2 — release/cutover parity audit

Date: 2026-08-09
Baseline: `074834d60b2647f18f32c43c4b6810ba91033b79`
Scope: user-visible Tkinter → PySide6 release parity and cutover readiness.

## Decision

**CUTOVER BLOCKED at REL-01.**

The PySide6 V2 application is ready for release hardening, but it is not yet safe to become the default launcher.

The blockers are release/runtime gates, not a request to restore every legacy automation feature:

1. production Qt startup does not currently create a V2 backup, although the V2 backup primitive and restore tests already exist;
2. clean shutdown/restart recovery is covered in pieces but not as one production-entrypoint lifecycle gate;
3. `install.bat` installs only `requirements.txt`, so a clean legacy install does **not** install PySide6;
4. `NemexiaRaidManager.spec` still packages `app_entry.py` and Tk/playwright/pystray-oriented dependencies rather than the Qt entrypoint;
5. no clean-install + existing-user side-by-side Windows release matrix currently proves Tk and Qt can coexist without crossing storage roots;
6. no explicit rollback/fallback test currently proves the legacy launcher remains usable if Qt cutover fails;
7. default `run_app.bat` still correctly launches `app_entry.py` and must remain unchanged until REL-02→REL-05 are green.

The parity audit also finds deliberate user-visible differences. They must be documented rather than silently reintroduced if they conflict with the V2 safety architecture.

## Release parity model

This audit uses four classifications:

- **PARITY** — the user goal exists in Qt with equivalent or safer V2 behavior.
- **SAFER REPLACEMENT** — the legacy workflow changed, but the same operational goal is supported through the V2 safety model.
- **INTENTIONAL EXCLUSION** — restoring the legacy affordance would violate an accepted V2 safety/navigation boundary.
- **FALLBACK-ONLY / DEFERRED** — useful legacy convenience not required for the first Qt default cutover; the explicit legacy fallback remains available until cleanup evidence says otherwise.

“User-visible parity” therefore does **not** mean recreating unsafe legacy browser automation byte-for-byte.

## User-visible parity matrix

| Area | Tkinter / `app_entry.py` | PySide6 V2 | Classification | Cutover consequence |
|---|---|---|---|---|
| Main shell | Dashboard/Plan/Active/Recon/Asteroids/Targets/History/Settings/Log plus patch-added Debris | Overview/Plan/Active/AutoFarm/Asteroids/Debris/Recon/Targets/History/Settings/Diagnostics | PARITY | none |
| Visual system | Orbital Command visual patches layered over Tk | frozen reusable Orbital Command Qt tokens/components | PARITY | none |
| Overview | KPI cards, recommended targets, active attacks, direct workflow buttons | persisted KPI/state, explicit live readiness and freshness | SAFER REPLACEMENT | direct action shortcuts intentionally moved to operation pages |
| Plan/queue | generate, prepare, send-next, checked wave, move/delete/clear/reset-stuck | deterministic V2 refill, read-only prepare, explicit selected dispatch, journal reconciliation | SAFER REPLACEMENT | no loss of supported V2 raid safety path; legacy manual queue surgery is fallback-only |
| Active flights | explicit sync, timers | explicit live refresh, capacity, unresolved journal, flight table | PARITY / SAFER REPLACEMENT | none |
| Auto raid | persisted legacy `auto_enabled`, tray notifications | explicit session-only arm, 30 s scheduler, exact safety-stop model | SAFER REPLACEMENT | intentionally does not persist armed state |
| Recon/report ingest | browser-wide import, file import, clean refresh/delete, full refresh | attach-only rendered report ingest + exact-fleet `processSpy` controlled refill | SAFER REPLACEMENT | file-import convenience deferred; destructive/bulk legacy routes excluded |
| Targets | search/filter + add/edit/delete + notes/flags | V2-owned/read-only targets with search/sort | FALLBACK-ONLY / DEFERRED | local target CRUD is not required for V2 evidence pipeline; must remain available through legacy fallback until separately migrated or explicitly retired |
| History | table + CSV export | read-only history table/search | FALLBACK-ONLY / DEFERRED | CSV export convenience is missing in Qt; not a browser/mutation blocker |
| Asteroids | configurable 39…1 scan, calculate/send wave, persisted auto-renew | attach-only current-system read, bounded prepare/dispatch, manual Stop | INTENTIONAL EXCLUSION + SAFER REPLACEMENT | automatic traversal/auto-renew must not return without a new navigation contract |
| Debris | legacy patch feature can scan/traverse and dispatch | current-system evidence + preparation token + confirmed shared asteroid dispatch | SAFER REPLACEMENT | automatic 3×40 remains excluded |
| Browser controls | launch Yandex, connect, global sync, save current page | no browser launch; attach-only explicit reads; Diagnostics has cached facts | INTENTIONAL EXCLUSION | `NO NAVIGATION BOUNDARY` remains authoritative |
| Logs/diagnostics | visible Log page + rotating file log + manual page snapshot | Diagnostics facts/paths; no dedicated live log viewer or capture action | FALLBACK-ONLY / DEFERRED | support convenience can be added later without blocking core cutover |
| Tray/minimize | optional tray, notifications, return alerts | normal Qt window close; no tray/return notification parity | FALLBACK-ONLY / DEFERRED | retain documented legacy fallback during first Qt release |
| Settings | broad legacy behavior/settings surface | allow-listed V2 connection/account/farm timing/action-gate settings | SAFER REPLACEMENT | obsolete/unsafe settings must not be imported merely for parity |
| Backup | backup on legacy startup and exit | backup primitive exists, but production `app_qt.py` does not call it | **BLOCKER** | REL-02 |
| Shutdown | save settings, stop tray, backup DB, close DB | `app_qt.main()` closes context/database in `finally`; debris workflow requests Stop/cancels unconfirmed preparation | PARTIAL / BLOCKER | lifecycle + backup/restart gate required |
| Runtime storage | `%LOCALAPPDATA%/NemexiaRaidManager/` | `%LOCALAPPDATA%/NemexiaRaidManagerV2/` | PARITY BY ISOLATION | side-by-side/upgrade tests required |
| Clean install | installs legacy requirements | PySide6 only in `requirements-v2.txt` | **BLOCKER** | REL-03 |
| Packaged EXE | PyInstaller entrypoint `app_entry.py` | spec not yet Qt-ready | **BLOCKER** | REL-03 |
| Rollback | current legacy launcher | rollback refs exist, but no release fallback test | **BLOCKER** | REL-05 |

## Tkinter features that must NOT be restored for parity

The following are not release blockers because they conflict with accepted V2 safety evidence:

- `Запустить браузер` / `launch_yandex()` from the app;
- app-owned tab creation or browser navigation;
- legacy galaxy/system traversal and 3×40 scans;
- legacy asteroid auto-renew when it requires automated system traversal/navigation;
- bulk or destructive spy-report flows such as deleting old spy messages or requesting all reports through legacy browser traversal;
- any legacy retry behavior that can repeat an ambiguous remote side effect;
- persisted auto-armed state after process restart;
- automatic CAPTCHA interaction.

V2-67 `NO NAVIGATION BOUNDARY` remains authoritative during release work.

## Safety-neutral legacy conveniences not present in Qt

These differences are real and user-visible, but they do not block the first safe Qt cutover as long as the tested fallback remains available and release docs name them explicitly:

- target add/edit/delete and notes/flags management;
- History CSV export;
- a dedicated live Log page;
- minimize-to-tray and return notifications;
- legacy manual queue reorder/delete/clear controls;
- file-based ZIP/HTML report import;
- manual page snapshot/capture UI.

None of these may be deleted from legacy code in REL-09 unless later evidence proves the replacement exists or the feature is explicitly retired.

## Production lifecycle findings

### What is already correct

`app_qt.py`:

- builds isolated V2 runtime paths;
- opens/migrates V2 schema through `V2Database`;
- imports legacy settings/queue/targets through read-only legacy storage;
- constructs attach-only browser adapters;
- closes the application context in a `finally` block.

`DebrisEnabledApplicationContext.close()` additionally:

- requests manual-stop semantics for the next debris action;
- cancels an unconfirmed prepared batch;
- closes debris source;
- delegates to parent close.

`V2Database.close()` closes SQLite deterministically.

### Missing release lifecycle contract

`create_v2_backup()` exists and is tested, but `app_qt.py` never calls it.

REL-02 must prove at minimum:

1. existing DB is preflighted and migrated before normal UI construction;
2. a consistent V2 backup is created at a deterministic production lifecycle point;
3. backup failure is fail-visible and must not silently corrupt/delete the live DB;
4. normal close releases SQLite and browser adapters;
5. restart reopens schema 9 and preserves settings, queue, raid/spy/asteroid/debris journals/evidence;
6. unresolved `pending`/`ambiguous` side effects remain blocking after restart;
7. a produced backup passes `PRAGMA integrity_check` and can be reopened/restored;
8. clean first start works with no legacy DB and no existing V2 DB.

## Windows install/package findings

Current source launcher/install path is still legacy by design:

- `run_app.bat` → `.venv\Scripts\python.exe app_entry.py`;
- `install.bat` installs `requirements.txt` only;
- `requirements-v2.txt` adds PySide6 but is not used by `install.bat`;
- `NemexiaRaidManager.spec` analyzes `app_entry.py` and explicitly collects legacy `pystray`/Tk-oriented support.

REL-03 must prepare Qt without changing the default launcher yet:

- install the dependency set needed by **both** legacy fallback and Qt during the side-by-side period;
- compile/smoke both entrypoints;
- prepare a Qt-capable PyInstaller spec/build path;
- keep legacy fallback executable/script addressable independently;
- keep `run_app.bat -> app_entry.py` until REL-06.

## Clean install / existing-user upgrade contract

REL-04 must use Windows CI with temporary `%LOCALAPPDATA%` roots and prove two scenarios.

### Clean install

- no legacy DB;
- no V2 DB;
- both entrypoints can start in controlled smoke mode without sharing mutable storage;
- Qt creates only `NemexiaRaidManagerV2` state;
- legacy creates/uses only `NemexiaRaidManager` state;
- no browser launch/navigation is triggered by the Qt smoke.

### Existing-user upgrade

- seed a representative legacy DB/settings/queue/recon state;
- start Qt against the same user profile;
- legacy DB bytes remain unchanged;
- V2 imports only the accepted migration inputs;
- V2 writes go only to V2 root;
- restart preserves imported + V2-owned state;
- legacy launcher still starts against the original legacy DB.

## Rollback/fallback contract

Before launcher cutover, REL-05 must prove:

- an explicit `run_legacy.bat` or equivalent stable fallback exists;
- default launcher can be changed without removing legacy fallback;
- fallback does not read/write V2 SQLite as its primary DB;
- Qt failure does not alter the fallback command;
- rollback refs remain untouched;
- a source-contract test pins the fallback entrypoint and storage boundary.

## Launcher cutover authorization

REL-06 may change `run_app.bat` to `app_qt.py` **only if** exact post-merge push-CI is green for REL-02, REL-03, REL-04 and REL-05.

The cutover PR must be small and auditable: launcher/default packaging metadata plus tests/docs needed to pin the new default. It must not contain browser/mutation work or legacy cleanup.

## Legacy cleanup rule

No Tkinter patch/runtime file is removable merely because Qt becomes default.

REL-08 must build a reachability/ownership inventory from:

- `app_entry.py` imports;
- legacy fallback launcher/spec;
- tests/self-test;
- docs/recovery tooling.

REL-09 may remove/archive only files proven unreachable from both the Qt release and the retained legacy fallback/support path. Ambiguous files stay.

## REL-01 conclusion

The correct next step is **REL-02 production lifecycle/backup/restart recovery**, not launcher cutover.

Default launcher remains legacy after this audit.
