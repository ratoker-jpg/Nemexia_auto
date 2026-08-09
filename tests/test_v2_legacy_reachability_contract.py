from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


DIRECT_ROLLBACK_MODULES = (
    "all_flight_slots_fix",
    "background_browser_fix",
    "bound_tab_fix",
    "command_planet_exclusion",
    "farm_flight_classification_fix",
    "farm_no_target_retry",
    "farm_runtime_reliability",
    "farm_wave_cooldown",
    "fleet_capacity_presentation",
    "fleet_capacity_settings_fallback",
    "flight_time_provenance_fix",
    "operational_variability",
    "queue_row_numbering",
    "raid_verification_fix",
    "report_time_freshness_fix",
    "resource_farm_auto",
    "resource_queue_modes",
    "ship_retry_fix",
    "tk_layout_compat",
    "visual_system",
    "visual_typography",
    "visual_layout",
    "visual_tables",
    "visual_motion",
    "debris_asteroids_feature",
    "page_capture",
)

REQUIRED_INSTALLATION_CALLS = (
    "install_bound_tab_fix()",
    "install_ship_retry_fix()",
    "install_raid_verification_fix()",
    "install_background_browser_fix()",
    "install_tk_layout_compat()",
    "prepare_visual_system(app_module)",
    "install_all_flight_slot_fix(BaseRaidManagerApp)",
    "install_command_planet_exclusion()",
    "install_report_time_freshness_fix(BaseRaidManagerApp)",
    "install_flight_time_provenance_fix()",
    "install_raid_home_selection(app_module.BrowserWorker)",
    "install_visual_system(app_module, BaseRaidManagerApp)",
    "install_typography(BaseRaidManagerApp)",
    "install_visual_layout(BaseRaidManagerApp)",
    "install_resource_queue_modes(BaseRaidManagerApp)",
    "install_asteroid_scope_ui(BaseRaidManagerApp)",
    "install_tables_dpi(BaseRaidManagerApp)",
    "install_queue_row_numbering(BaseRaidManagerApp)",
    "install_resource_farm_auto(BaseRaidManagerApp)",
    "install_farm_no_target_retry(BaseRaidManagerApp)",
    "install_farm_flight_classification_fix(BaseRaidManagerApp)",
    "install_farm_capacity_fix(app_module.BrowserWorker, BaseRaidManagerApp)",
    "install_farm_wave_cooldown(BaseRaidManagerApp)",
    "install_farm_ui_fix(BaseRaidManagerApp)",
    "install_fleet_capacity_presentation(BaseRaidManagerApp)",
    "install_fleet_capacity_settings_fallback(app_module.BrowserWorker, BaseRaidManagerApp)",
    "install_motion(BaseRaidManagerApp)",
    "install_debris_layout(debris_module)",
    "debris_module.install_debris_asteroid_feature(BaseRaidManagerApp)",
)


def test_legacy_runtime_has_two_explicit_source_roots_and_qt_stays_default() -> None:
    default = text("run_app.bat")
    fallback = text("run_legacy.bat")
    console = text("run_console.bat")

    assert '"%VENV_PY%" app_qt.py %*' in default
    assert "app_entry.py" not in default
    assert '"%VENV_PY%" app_entry.py %*' in fallback
    assert '"%VENV_PY%" app_entry.py' in console


def test_every_direct_app_entry_patch_module_is_present_imported_and_installed() -> None:
    entry = text("app_entry.py")
    for module in DIRECT_ROLLBACK_MODULES:
        assert (ROOT / f"{module}.py").is_file(), f"retained rollback module missing: {module}.py"
        assert module in entry, f"app_entry.py no longer reaches retained rollback module: {module}"

    for installation_call in REQUIRED_INSTALLATION_CALLS:
        assert installation_call in entry, f"rollback installer invocation missing: {installation_call}"


def test_legacy_core_transitive_modules_remain_available_for_fallback_and_self_test() -> None:
    entry = text("app_entry.py")
    app = text("app.py")
    browser = text("browser.py")
    self_test = text("self_test.py")

    assert "import app as app_module" in entry
    for module in ("browser", "config", "models", "reports", "storage", "ui_utils"):
        assert (ROOT / f"{module}.py").is_file()
        assert module in app
    assert "from asteroids import" in browser
    for required in ("from app import RaidManagerApp", "from browser import", "from storage import Database", "from asteroids import"):
        assert required in self_test


def test_monkey_patch_reachability_is_not_treated_as_static_dead_code() -> None:
    background = text("background_browser_fix.py")
    bound = text("bound_tab_fix.py")
    command_planet = text("command_planet_exclusion.py")

    assert "browser_module.launch_yandex = launch_yandex_background" in background
    assert "BrowserWorker._ensure_fleets_page = _ensure_fleets_page_background" in background
    assert "BrowserWorker._ensure_galaxy_page = _ensure_galaxy_page_background" in background
    assert "BrowserWorker.connect" in bound
    assert "BrowserWorker._select_nemexia_page" in bound
    assert "BrowserWorker.sync_all_flights = sync_all_flights" in command_planet
    assert "Database.add_history = add_history" in command_planet


def test_legacy_package_build_and_data_roots_are_retained() -> None:
    spec = text("NemexiaRaidManagerLegacy.spec")
    build = text("build_legacy_exe.bat")
    install = text("install.bat")
    requirements_v2 = text("requirements-v2.txt")
    requirements = text("requirements.txt")

    assert "['app_entry.py']" in spec
    assert "collect_all('playwright')" in spec
    assert "collect_all('bs4')" in spec
    assert "collect_all('pystray')" in spec
    assert "('targets_seed.json', '.')" in spec
    assert "('assets/nemexia.ico', 'assets')" in spec
    assert "PIL._tkinter_finder" in spec
    assert "NemexiaRaidManagerLegacy.spec" in build
    assert 'import app_entry' in build
    assert "app_entry.py" in install and "self_test.py" in install
    assert '"%VENV_PY%" self_test.py' in install
    assert "-r requirements.txt" in requirements_v2
    for dependency in ("playwright", "beautifulsoup4", "pystray", "Pillow"):
        assert dependency in requirements


def test_release_ci_keeps_legacy_fallback_and_self_test_as_live_gates() -> None:
    workflow = text(".github/workflows/ci.yml")
    fallback_smoke = text("ci/release_fallback_smoke.py")
    harness = text("ci/run_legacy_self_test.py")

    assert "Run legacy self-test" in workflow
    assert "python ci/run_legacy_self_test.py" in workflow
    assert "Run explicit legacy fallback smoke" in workflow
    assert "release_fallback_smoke.py" in workflow
    assert '"run_legacy.bat", "--release-smoke"' in fallback_smoke
    assert "import self_test" in harness


def test_real_saved_page_evidence_used_by_v2_safety_gate_is_retained() -> None:
    fixture = ROOT / "saved_pages" / "2026-08-08_08-54-11-072" / "page.html"
    consumer = text("tests/test_v2_fourth_batch_safety.py")
    assert fixture.is_file()
    assert 'saved_pages" / "2026-08-08_08-54-11-072" / "page.html' in consumer
