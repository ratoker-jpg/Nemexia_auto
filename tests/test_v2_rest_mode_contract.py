from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "v2/application/rest_mode.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2/application/rest_mode_context.py").read_text(encoding="utf-8")
READER = (ROOT / "v2/infrastructure/cdp_rest_mode_reader.py").read_text(encoding="utf-8")
SESSIONS = (ROOT / "v2/infrastructure/cdp_mutation_sessions.py").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "v2/persistence/rest_mode.py").read_text(encoding="utf-8")
APP = (ROOT / "app_qt.py").read_text(encoding="utf-8")
WINDOW = (ROOT / "v2/ui/main_window.py").read_text(encoding="utf-8")


def test_rest_mode_runtime_is_typed_and_has_no_application_browser_selectors() -> None:
    for token in (
        "RestModeService",
        "BrowserReadinessManager",
        "NavigationCoordinator",
        "RestModeRepository",
        "RestModeApplicationContext",
        "REST_MODE_OWNER",
        "CAPTCHA_REQUIRED",
        "BLOCKED_BROWSER",
        "BLOCKED_IDENTITY",
        "BLOCKED_AMBIGUOUS",
        "UNVERIFIED_DATA_REQUIRED",
    ):
        assert token in SERVICE + CONTEXT + PERSISTENCE + APP

    for forbidden in (
        "playwright",
        "query_selector",
        "locator(",
        "page.evaluate",
        ".goto(",
        "SendFleet(",
        "processSpy(",
    ):
        assert forbidden not in SERVICE
        assert forbidden not in CONTEXT


def test_reader_requires_rendered_human_readable_activity_minutes() -> None:
    assert "Автоматический\\s+режим\\s+проверки\\s+через" in READER
    assert "raw BOT_CHECK units are intentionally ignored" in READER
    assert "BOT_CHECK / 60" not in READER
    assert "BOT_CHECK/60" not in READER
    assert "int(window.BOT_CHECK" not in READER
    assert "BOTCHECK_PAGE_LOCK" in READER
    assert "recaptcha" in READER.casefold()
    assert "bot_check.php" in READER


def test_rest_mode_reuses_navigation_owned_backend_and_has_no_attack_parser() -> None:
    assert "OwnedRestModeReadMixin" in SESSIONS
    assert "V2AutomaticReconCdpBackendNoAutoReconnect" in APP
    assert "browser=navigation_backend" in APP
    assert "navigation=navigation" in APP
    assert "ReadOnlyDebrisCdpBackend" in APP  # unrelated existing read source stays separate
    for forbidden in (
        "incoming_attack",
        "attack_selector",
        "fleet_id + arrival",
        "SendFleet",
    ):
        assert forbidden not in READER


def test_component_schema_does_not_modify_core_v2_schema_version() -> None:
    assert "rest_mode_schema_migrations" in PERSISTENCE
    assert "REST_MODE_SCHEMA_VERSION = 1" in PERSISTENCE
    assert "SCHEMA_VERSION" not in PERSISTENCE.replace("REST_MODE_SCHEMA_VERSION", "")


def test_startup_is_disarmed_and_driver_never_arms_rest_mode() -> None:
    driver = (ROOT / "v2/infrastructure/qt_rest_mode_driver.py").read_text(encoding="utf-8")
    assert "disarm_on_startup()" in SERVICE
    assert "rest_mode_state" in driver
    assert "tick_rest_mode" in driver
    assert "start_rest_mode" not in driver
    assert "tick_asteroid_autorenew" not in driver


def test_runtime_pr_adds_no_visible_rest_mode_controls() -> None:
    for forbidden in (
        "StartRestModeButton",
        "StopRestModeButton",
        "Запустить Rest Mode",
        "Остановить Rest Mode",
        '"rest_mode", "Режим отдыха"',
    ):
        assert forbidden not in WINDOW
    assert "QtRestModeDriver" in WINDOW


def test_context_holds_authority_through_service_stop_and_blocks_browser_entries() -> None:
    assert "return service.stop(detail=detail)" in CONTEXT
    assert "finally:" in CONTEXT
    assert "self.release_automation_cycle(REST_MODE_OWNER)" in CONTEXT
    assert "_require_rest_mode_browser_available" in CONTEXT
    for entry in (
        "ensure_fleets_ready",
        "ensure_messages_ready",
        "ensure_galaxy_ready",
        "process_spy",
        "run_automatic_recon",
        "step_discovery_scan",
        "dispatch_asteroid",
        "confirm_debris_candidates",
    ):
        assert f"def {entry}" in CONTEXT
