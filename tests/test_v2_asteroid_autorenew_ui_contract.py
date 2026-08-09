from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "v2/ui/pages/asteroids_autorenew.py").read_text(encoding="utf-8")
WINDOW = (ROOT / "v2/ui/main_window.py").read_text(encoding="utf-8")
BASE_PAGE = (ROOT / "v2/ui/pages/asteroids.py").read_text(encoding="utf-8")


def test_shell_routes_to_ui_only_autorenew_overlay() -> None:
    assert "from v2.ui.pages.asteroids_autorenew import AsteroidsPage" in WINDOW
    assert "class AsteroidsPage(ManualAsteroidsPage):" in PAGE
    assert "from v2.ui.pages.asteroids import AsteroidsPage as ManualAsteroidsPage" in PAGE


def test_autorenew_surface_exposes_explicit_start_stop_and_requested_state_fields() -> None:
    for token in (
        "StartAsteroidAutorenewButton",
        "StopAsteroidAutorenewButton",
        '"ARMED"',
        '"STOPPED"',
        '"BLOCKED"',
        '"AMBIGUOUS"',
        '"ERROR"',
        "AutorenewProgress",
        "AutorenewCurrentSystem",
        "AutorenewNextCycle",
        "AutorenewLastReturn",
        "AutorenewLastResult",
        'f"{progress}/120"',
        "DISCOVERY_SEQUENCE",
    ):
        assert token in PAGE


def test_autorenew_ui_uses_typed_context_only() -> None:
    for typed_call in (
        'getattr(self.context, "asteroid_autorenew_state", None)',
        'getattr(self.context, "discovery_scan", None)',
        'getattr(self.context, "start_asteroid_autorenew", None)',
        'getattr(self.context, "stop_asteroid_autorenew", None)',
        'self.context.v2_setting("farm_return_buffer_minutes", 5)',
    ):
        assert typed_call in PAGE

    for forbidden in (
        "playwright",
        "CDP",
        "V2AutorenewAsteroidCdpBackend",
        "V2AsteroidCdpBackend",
        "page.evaluate",
        ".goto(",
        "query_selector",
        "locator(",
        "#galaxyHolder",
        "ajax_galaxy.php",
        "SendFleet(",
        "tick_asteroid_autorenew",
        "AsteroidAutorenewRepository",
        "install_asteroid_autorenew_schema",
    ):
        assert forbidden not in PAGE


def test_ui_timer_is_presentation_polling_not_a_second_scheduler() -> None:
    assert "self.startTimer(1000)" in PAGE
    assert "def timerEvent(self, event)" in PAGE
    assert "self._refresh_autorenew_status()" in PAGE
    assert "tick_asteroid_autorenew" not in PAGE
    assert "while True" not in PAGE
    assert "sleep(" not in PAGE


def test_manual_asteroid_contract_remains_separate_and_unchanged_in_role() -> None:
    for token in (
        "ReadAsteroidsButton",
        "PrepareAsteroidsButton",
        "DispatchAsteroidsButton",
        "StopAsteroidsButton",
        "should_stop=self._poll_manual_stop",
        "AsteroidWorkflowState.STOPPED_MANUAL",
    ):
        assert token in BASE_PAGE
    assert "start_asteroid_autorenew" not in BASE_PAGE
    assert "stop_asteroid_autorenew" not in BASE_PAGE
