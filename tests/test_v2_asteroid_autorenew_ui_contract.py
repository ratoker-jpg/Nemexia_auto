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


def test_manual_and_autorenew_controls_are_interlocked_in_ui() -> None:
    assert "def _manual_controls(self):" in PAGE
    assert "def _sync_control_interlock(self, state, *, state_unknown: bool)" in PAGE
    assert "manual_locked = state_unknown or autorenew_armed" in PAGE
    assert "and not self._series_running" in PAGE
    assert "if self._series_running:" in PAGE
    assert "def _set_series_controls(self, running: bool)" in PAGE
    for widget in (
        "self.read_button",
        "self.prepare_button",
        "self.send_button",
        "self.source_coord",
        "self.recycler_count",
        "self.safety_seconds",
        "self.table",
    ):
        assert widget in PAGE


def test_transient_typed_failure_keeps_last_error_but_reconciles_controls() -> None:
    assert 'self._autorenew_last_error = ""' in PAGE
    assert "self._autorenew_last_error = state_error" in PAGE
    assert "self._sync_control_interlock(state, state_unknown=False)" in PAGE
    assert "latest successfully-read state" in PAGE
    assert "authoritative state:" in PAGE


def test_progress_failure_does_not_discard_authoritative_scheduler_state() -> None:
    state_read = PAGE.index("state = self._typed_autorenew_state()")
    scan_read = PAGE.index("scan = self._typed_discovery_scan")
    assert state_read < scan_read
    assert 'scan_error = ""' in PAGE
    assert 'self._autorenew_values["AutorenewProgress"].setText("—/120")' in PAGE
    assert "A discovery progress read is ancillary" in PAGE
    assert "self._sync_control_interlock(state, state_unknown=False)" in PAGE
    assert "Autorenew state подтверждён" in PAGE


def test_start_gate_allows_recoverable_blocked_but_rejects_retained_scan() -> None:
    assert "if str(state.status) in cls._AMBIGUOUS_STATUSES:" in PAGE
    assert 'if getattr(state, "active_scan_id", None):' in PAGE
    assert "Safe BLOCKED states" in PAGE
    assert "typed service revalidates readiness on every Start" in PAGE


def test_zero_minute_return_buffer_is_not_replaced_by_default() -> None:
    assert 'int(self.context.v2_setting("farm_return_buffer_minutes", 5))' in PAGE
    assert 'v2_setting("farm_return_buffer_minutes", 5) or 5' not in PAGE


def test_current_system_tracks_last_completed_discovery_system() -> None:
    assert "DISCOVERY_SEQUENCE[min(cursor, len(DISCOVERY_SEQUENCE)) - 1]" in PAGE
    assert 'return f"ожидает {galaxy}:{solar}"' in PAGE
    assert 'str(state.status) == "waiting_return"' in PAGE


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
