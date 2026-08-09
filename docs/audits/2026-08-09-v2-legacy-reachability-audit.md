# Nemexia Raid Manager V2 — REL-08 legacy reachability audit

Date: 2026-08-09
Audit baseline: `fd0992bb8eba2d236ffb867e4a034c2aa15b1153`
Baseline release gate: PR #122 / REL-07, exact push-CI #278 = green.
Scope: retained Tkinter fallback/runtime, support/build/test reachability after the Qt-default cutover.

## Decision

**No production legacy file is proven dead at this baseline.**

`D. PROVEN DEAD = ∅`.

REL-09 therefore must be an intentional **NO-OP / HARDENING** stage: retain the tested Tkinter rollback stack and add/keep regression contracts that prevent accidental removal. It must not invent cleanup merely because Qt is now the default runtime.

This result follows the release rule `UNKNOWN != DEAD`. Several legacy modules are dynamically installed monkey patches whose effect depends on import/install order, and the legacy fallback is still an explicitly built, black-box-tested product surface.

## Classification model

- **A. REQUIRED BY LEGACY FALLBACK** — reachable from a retained legacy runtime root or legacy package.
- **B. SHARED** — required by both release worlds or by shared install/package infrastructure.
- **C. TEST/DOC/BUILD ONLY** — not required by normal runtime but intentionally retained for validation, evidence, documentation or build/release operations.
- **D. PROVEN DEAD** — no runtime/build/test/docs reachability and safe deletion is positively demonstrated.
- **E. UNKNOWN / DYNAMICALLY REACHABLE** — exact reachability/ownership is not sufficiently proven; must be retained.

## Authoritative reachability roots

The audit uses all of these roots, not only the new Qt default:

1. `run_legacy.bat -> app_entry.py` — supported source rollback launcher.
2. `run_console.bat -> app_entry.py` — second retained direct legacy runtime launcher.
3. `NemexiaRaidManagerLegacy.spec -> app_entry.py` — supported packaged rollback executable.
4. `build_legacy_exe.bat -> NemexiaRaidManagerLegacy.spec` — supported legacy build path.
5. `install.bat` — installs the shared Qt+legacy environment, compiles legacy core sources and runs `self_test.py`.
6. `ci/run_legacy_self_test.py -> self_test.py` — mandatory CI gate on Python 3.10 and 3.11.
7. `ci/release_fallback_smoke.py -> run_legacy.bat --release-smoke` — black-box rollback release gate.
8. legacy and V2 pytest contracts, including the real saved-page fixture used by capacity tests.
9. documentation/evidence and recovery/support tooling where repository ownership is still intentional.

The production default remains separately rooted at `run_app.bat -> app_qt.py`; it does not make the rollback roots unreachable.

## Runtime graph: `app_entry.py`

`app_entry.py` imports and installs the patch/runtime modules below before constructing the legacy app. Several installers mutate `BrowserWorker`, `Database`, `RaidManagerApp`, imported module globals, or Tk widget behavior. Import order is therefore part of the runtime contract.

Direct imports/installers from `app_entry.py`:

- `all_flight_slots_fix.py`
- `background_browser_fix.py`
- `bound_tab_fix.py`
- `command_planet_exclusion.py`
- `farm_flight_classification_fix.py`
- `farm_no_target_retry.py`
- `farm_runtime_reliability.py`
- `farm_wave_cooldown.py`
- `fleet_capacity_presentation.py`
- `fleet_capacity_settings_fallback.py`
- `flight_time_provenance_fix.py`
- `operational_variability.py`
- `queue_row_numbering.py`
- `raid_verification_fix.py`
- `report_time_freshness_fix.py`
- `resource_farm_auto.py`
- `resource_queue_modes.py`
- `ship_retry_fix.py`
- `tk_layout_compat.py`
- `visual_system.py`
- `visual_typography.py`
- `visual_layout.py`
- `visual_tables.py`
- `visual_motion.py`
- `debris_asteroids_feature.py`
- `page_capture.py`
- `app.py`

Examples of non-static reachability:

- `background_browser_fix.install_background_browser_fix()` replaces `browser_module.launch_yandex`, `BrowserWorker._ensure_fleets_page` and `BrowserWorker._ensure_galaxy_page` before `app.py` imports the patched browser symbol.
- `bound_tab_fix` wraps/replaces page-selection and connect behavior.
- `command_planet_exclusion` patches both `BrowserWorker` and `Database`, and performs an inner `from models import parse_dt`.
- visual/farm modules wrap Tk application classes and depend on installation order called by `app_entry.py`.

Consequently, a module that looks like an isolated `*_fix.py` file cannot be classified dead from a simple static call-site count.

## Transitive legacy core

`app.py` imports the following live legacy core modules:

- `browser.py`
- `config.py`
- `models.py`
- `reports.py`
- `storage.py`
- `ui_utils.py`

`browser.py` in turn imports `asteroids.py`, `config.py`, `models.py` and `reports.py` plus Playwright.

`debris_asteroids_feature.py` imports `app`, `asteroids`, `browser`, `models` and `ui_utils` and is installed by `app_entry.py`.

`page_capture.py` is invoked by the legacy UI to save manual screenshot/HTML/MHTML snapshots.

These files remain part of the supported fallback even where a corresponding legacy capability is deliberately excluded from V2. A capability being excluded from V2 does **not** make its rollback implementation dead.

## PyInstaller / data / dependency reachability

`NemexiaRaidManagerLegacy.spec` explicitly packages:

- entrypoint `app_entry.py`;
- Playwright data/binaries/hidden imports;
- BeautifulSoup data/binaries/hidden imports;
- pystray data/binaries/hidden imports;
- `targets_seed.json`;
- `assets/nemexia.ico`;
- `PIL._tkinter_finder`, `PIL.Image`, `PIL.ImageTk`, `soupsieve` hidden imports.

`requirements-v2.txt` intentionally includes `requirements.txt`, so the current clean-install environment contains the retained legacy requirements plus PySide6. `requirements-build.txt` includes `requirements-v2.txt` plus PyInstaller.

The fallback package and its dependency/data surface are therefore live release inputs.

## CI/test reachability

`self_test.py` directly imports and exercises `app`, `browser`, `reports`, `storage`, `models` and `asteroids`, and reads `targets_seed.json` plus report fixtures.

The main CI runs the legacy self-test on Windows Python 3.10 and 3.11. The Windows release black-box job separately executes the explicit legacy fallback.

`tests/test_v2_fourth_batch_safety.py` reads `saved_pages/2026-08-08_08-54-11-072/page.html` as real fleets evidence and checks `FleetsCount` / `MaxFleets` selectors. That saved page is therefore test evidence, not dead repository data.

The root legacy `test_*.py` files and `tests/test_*` legacy visual/patch contracts directly exercise the retained patch stack.

## File inventory

### A. REQUIRED BY LEGACY FALLBACK

| File | Reachability evidence |
|---|---|
| `run_legacy.bat` | explicit rollback launcher; black-box tested |
| `run_console.bat` | directly launches `app_entry.py` |
| `app_entry.py` | rollback source/package entrypoint |
| `app.py` | imported by `app_entry.py`; legacy Tk application |
| `browser.py` | imported by `app.py` and patches; Playwright runtime |
| `config.py` | imported by legacy core; owns legacy storage/profile/resource paths |
| `storage.py` | legacy DB runtime; imported by app and patches |
| `models.py` | legacy domain types used by app/browser/storage/tests |
| `reports.py` | legacy report parser used by app/browser/self-test |
| `asteroids.py` | imported by `browser.py`; legacy asteroid calculations |
| `ui_utils.py` | imported by legacy UI/features |
| `all_flight_slots_fix.py` | direct `app_entry.py` installer |
| `background_browser_fix.py` | direct installer; mutates browser module/worker methods |
| `bound_tab_fix.py` | direct installer; mutates BrowserWorker binding methods |
| `command_planet_exclusion.py` | direct installer; mutates BrowserWorker/Database |
| `farm_flight_classification_fix.py` | direct installer and dependency of farm reliability |
| `farm_no_target_retry.py` | direct installer |
| `farm_runtime_reliability.py` | direct installer; imports other farm/visual patches |
| `farm_wave_cooldown.py` | direct installer |
| `fleet_capacity_presentation.py` | direct installer |
| `fleet_capacity_settings_fallback.py` | direct installer |
| `flight_time_provenance_fix.py` | direct installer |
| `operational_variability.py` | direct installers for legacy runtime |
| `queue_row_numbering.py` | direct installer |
| `raid_verification_fix.py` | eager installer before `app` import |
| `report_time_freshness_fix.py` | direct installer |
| `resource_farm_auto.py` | direct installer; farm dependency |
| `resource_queue_modes.py` | direct installer |
| `ship_retry_fix.py` | eager installer before `app` import |
| `tk_layout_compat.py` | direct Tk compatibility installer before UI creation |
| `visual_system.py` | direct presentation installer and dependency of other patches |
| `visual_typography.py` | direct installer |
| `visual_layout.py` | direct installer, including debris layout patch |
| `visual_tables.py` | direct installer |
| `visual_motion.py` | direct installer |
| `debris_asteroids_feature.py` | imported and installed into rollback UI |
| `page_capture.py` | rollback UI manual page-capture action |
| `targets_seed.json` | legacy config seed + legacy PyInstaller data |
| `NemexiaRaidManagerLegacy.spec` | supported packaged fallback definition |
| `build_legacy_exe.bat` | supported fallback build command |

### B. SHARED

| File/group | Why shared |
|---|---|
| `install.bat` | creates one environment for Qt default and Tk fallback; compiles both and runs legacy self-test |
| `requirements.txt` | retained legacy deps; included by V2 environment |
| `requirements-v2.txt` | includes legacy requirements + PySide6 |
| `requirements-build.txt` | shared build dependency chain |
| `launcher_messages.ps1` | messages used by default/fallback/build launchers |
| `assets/nemexia.ico` | data/icon for both Qt and legacy specs |
| `.venv` contract / Python 3.10–3.11 support | shared installation/runtime contract, not repository code |

Root legacy modules such as `models.py` are not labeled B merely because V2 represents similar concepts: current V2 code has its own `v2.domain` model layer. Their current positive reachability is through the fallback and tests, so A is the stronger classification.

### C. TEST / DOC / BUILD ONLY

| File/group | Reachability |
|---|---|
| `.github/workflows/ci.yml` | release validation workflow |
| `ci/qt_smoke.py` | Qt visual/runtime gate |
| `ci/release_default_launcher_smoke.py` | Qt default black-box gate |
| `ci/release_fallback_smoke.py` | explicit legacy rollback black-box gate |
| `ci/release_side_by_side_smoke.py` | clean install + existing-user upgrade gate |
| `ci/run_legacy_self_test.py` | Windows legacy self-test harness |
| `self_test.py`, `self_test.bat` | mandatory legacy regression validation |
| root `test_*.py` | legacy patch/runtime tests |
| `tests/**` | V2 + legacy + cutover regression contracts |
| `saved_pages/2026-08-08_08-54-11-072/page.html` | real fleets evidence fixture used by V2 safety test |
| `docs/**`, `REPORT_*.md`, `README_RU.md`, `CHANGELOG.md` | repository documentation/audit/evidence |
| `NemexiaRaidManager.spec`, `NemexiaRaidManagerQt.spec` | Qt/default package definitions |
| `build_exe.bat`, `build_qt_exe.bat` | default/alternate Qt build commands |
| `run_qt.bat` | explicit Qt launch convenience |
| `launcher.bat` | production convenience wrapper around `run_app.bat` |
| `pull_from_github.bat`, `push_to_github.bat` | repository maintenance tooling |

`launcher.bat` is user-visible release tooling rather than application-module reachability; it is retained regardless of the legacy cleanup question.

### D. PROVEN DEAD

**None.**

No production legacy module satisfies the required positive proof of having no runtime, build, test, docs/support, package, monkey-patch or dynamic reachability.

### E. UNKNOWN / DYNAMICALLY REACHABLE

| File/group | Reason to retain |
|---|---|
| older committed `saved_pages/**` snapshots not named by current tests | historical/evidence ownership has not been individually proven removable |
| `preview.png` | repository presentation/evidence purpose exists but current consumer was not positively established |
| `VERIFICATION.txt` | support/release provenance purpose is not sufficiently classified for deletion |

The dynamic monkey-patch modules themselves are classified A because their installers are directly called; E is reserved here for artifacts whose ownership cannot be positively resolved from current release roots.

## Cleanup decision for REL-09

REL-09 is **not authorized to delete any legacy production file** from this audit.

Required REL-09 behavior:

1. retain `run_legacy.bat -> app_entry.py`;
2. retain `run_console.bat -> app_entry.py` while it exists as a supported launcher;
3. retain the complete direct `app_entry.py` patch/import set;
4. retain legacy core `app/browser/config/storage/models/reports/asteroids/ui_utils`;
5. retain `NemexiaRaidManagerLegacy.spec` and `build_legacy_exe.bat`;
6. retain legacy self-test and release fallback smoke;
7. add/strengthen a source-contract that fails if these rollback roots or direct installer modules disappear;
8. make no deletion solely to reduce file count.

Future cleanup requires a new audit with new evidence, especially if the legacy fallback is formally retired. That is outside this release batch.

## Safety boundaries

REL-08 does not authorize or re-enable any legacy behavior in V2. The following remain separate V2 limitations/contracts:

- `NO NAVIGATION BOUNDARY`;
- no automatic 3×40 traversal;
- no background browser navigation in V2;
- no Rest Mode navigation loop;
- no automatic `refreshGalaxy`;
- no V2 `change_planet.php`;
- no arbitrary V2 `page.goto`;
- CAPTCHA detect → STOP, never solve/click/bypass;
- no automatic message deletion;
- no automatic retry after an ambiguous remote side effect;
- no creation of a new espionage route without an exact processable spy fleet;
- no unattended asteroid/debris scheduler.

The existence of legacy implementations behind an explicit rollback launcher does not change the Qt/V2 safety contract.
