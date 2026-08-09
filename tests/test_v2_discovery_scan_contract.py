from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app_qt.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "v2/application/discovery_scan.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2/application/automation_context.py").read_text(encoding="utf-8")
READER = (ROOT / "v2/infrastructure/cdp_discovery_reader.py").read_text(encoding="utf-8")
SESSIONS = (ROOT / "v2/infrastructure/cdp_mutation_sessions.py").read_text(encoding="utf-8")
PERSISTENCE = (ROOT / "v2/persistence/discovery_scan.py").read_text(encoding="utf-8")


def test_auto10_uses_same_owned_browser_backend_as_navigation() -> None:
    assert "OwnedDiscoveryReadMixin" in SESSIONS
    assert "V2AutomaticReconCdpBackendNoAutoReconnect" in APP
    assert "browser=navigation_backend" in APP
    assert "navigation=navigation" in APP
    assert "DiscoveryScanRepository(database)" in APP
    assert "AsteroidObservationRepository(database)" in APP
    assert "V2DebrisRepository(database)" in APP


def test_discovery_reader_is_read_only_current_system_evidence() -> None:
    for token in (
        "_validate_expected_context",
        "#galaxyHolder",
        "#c1",
        "#c2",
        "ajax_info.php",
        "squareInfo",
        "CAPTCHA",
        "holder.querySelectorAll('img')",
        "unparseableAsteroids",
        "_validated_visible_asteroid_coords",
    ):
        assert token in READER
    for forbidden in (
        ".goto(",
        "new_page(",
        "window.refreshGalaxy",
        "processSpy(",
        "SendFleet",
    ):
        assert forbidden not in READER


def test_application_scan_layer_has_no_browser_selectors_or_cdp_imports() -> None:
    for forbidden in (
        "playwright",
        "connect_over_cdp",
        "document.querySelector",
        "#galaxyHolder",
        "ajax_info.php",
        "squareInfo",
        "refreshGalaxy",
    ):
        assert forbidden not in SERVICE
        assert forbidden not in CONTEXT


def test_persistent_contract_requires_all_120_systems_for_last_completed() -> None:
    assert "DISCOVERY_SYSTEM_COUNT = 120" in PERSISTENCE
    assert "cursor_index != DISCOVERY_SYSTEM_COUNT" in PERSISTENCE
    assert "count != DISCOVERY_SYSTEM_COUNT" in PERSISTENCE
    assert "WHERE status='completed' AND cursor_index=?" in PERSISTENCE
    assert "UNIQUE(scan_id, galaxy, solar)" in PERSISTENCE


def test_review_gates_precede_readiness_and_competing_resume_is_repository_wide() -> None:
    assert CONTEXT.count("self._require_discovery_navigation_clear()") >= 2
    assert "zero new browser mutations attempted" in CONTEXT
    assert "scan_id<>? AND status IN ('running','ambiguous')" in PERSISTENCE
    assert "Discovery resume blocked by unresolved" in PERSISTENCE


def test_auto10_exposes_typed_start_stop_resume_step_without_ui_browser_logic() -> None:
    for token in (
        "start_discovery_scan",
        "resume_discovery_scan",
        "stop_discovery_scan",
        "step_discovery_scan",
        "run_discovery_scan",
        "last_completed_discovery_scan",
    ):
        assert token in CONTEXT
    assert "v2/ui/" not in APP
