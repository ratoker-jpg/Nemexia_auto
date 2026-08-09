from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app_qt.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "v2/application/automatic_recon.py").read_text(encoding="utf-8")
BACKEND = (ROOT / "v2/infrastructure/cdp_automatic_recon.py").read_text(encoding="utf-8")
UI = (ROOT / "v2/ui/pages/recon.py").read_text(encoding="utf-8")


def test_auto07_uses_exact_link_timer_and_one_process_spy_call() -> None:
    assert "spy1Link-" in BACKEND
    assert "spy1Time-" in BACKEND
    assert BACKEND.count("window.processSpy(Number(fleetId));") == 1
    assert "closest('tr')" in BACKEND


def test_auto07_backend_does_not_restore_bulk_or_own_navigation() -> None:
    for forbidden in (
        "processSpy(0)",
        "SendFleet",
        "new_page(",
        ".goto(",
        "loadTabContent",
        "refreshGalaxy",
    ):
        assert forbidden not in BACKEND
    assert "V2NavigationCdpBackend" in BACKEND


def test_application_layer_has_no_browser_selectors_or_cdp_calls() -> None:
    for forbidden in (
        "playwright",
        "connect_over_cdp",
        "#spy1Link-",
        "#spy1Time-",
        "document.querySelector",
        "window.processSpy",
    ):
        assert forbidden not in SERVICE


def test_verification_polls_reads_without_opening_a_second_mutation_window() -> None:
    assert "verification_timeout_seconds: float = 10.0" in SERVICE
    assert "verification_poll_seconds: float = 0.4" in SERVICE
    assert "deadline = time.monotonic() + self.verification_timeout_seconds" in SERVICE
    assert "while True:" in SERVICE
    assert SERVICE.count("self.browser.process_spy_once(") == 1


def test_manual_spy_interlock_queries_any_unresolved_row_without_history_limit() -> None:
    assert "WHERE status IN ('pending','ambiguous')" in SERVICE
    assert "ORDER BY id DESC LIMIT 1" in SERVICE
    assert "list_spy_actions(limit=500)" not in SERVICE


def test_production_shares_one_backend_between_navigation_and_auto_recon() -> None:
    assert "navigation_backend = V2AutomaticReconCdpBackendNoAutoReconnect(endpoint.endpoint)" in APP
    assert "NavigationCoordinator(\n            navigation_backend," in APP
    assert "AutomaticReconService(\n            navigation_backend," in APP
    assert "AutomaticReconJournalRepository(database)" in APP


def test_automation_pr_keeps_existing_manual_recon_ui_for_separate_ui_followup() -> None:
    # AUTO-07 business logic must not smuggle selectors/CDP into Qt. The current
    # manual fleet-id widget remains until a separate UI-only follow-up removes it.
    assert "self.fleet_id = QLineEdit" in UI
    assert "PySide6" not in SERVICE
    assert "PySide6" not in BACKEND
