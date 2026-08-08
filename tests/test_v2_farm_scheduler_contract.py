from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FARM = (ROOT / "v2" / "ui" / "pages" / "farm.py").read_text(encoding="utf-8")
CONTROLLER = (ROOT / "v2" / "application" / "farm_controller.py").read_text(encoding="utf-8")


def test_scheduler_is_explicitly_armed_and_never_persisted() -> None:
    assert "QTimer" in FARM
    assert "SCHEDULER_INTERVAL_MS = 30_000" in FARM
    assert "self._armed = False" in FARM
    assert "def start_cycle" in FARM
    assert "QMessageBox.question" in FARM
    assert "self._timer.start()" in FARM
    assert "self._timer.stop()" in FARM
    assert "НЕ включается автоматически после перезапуска" in FARM
    for forbidden in (
        "farm_auto_enabled",
        "scheduler_enabled",
        "set_v2_setting",
        "set_v2_settings",
    ):
        assert forbidden not in FARM


def test_scheduler_hard_stops_on_uncertainty_or_live_failure() -> None:
    assert "FarmState.BLOCKED_UNRESOLVED" in FARM
    assert "FarmState.LIVE_UNAVAILABLE" in FARM
    assert "result.stopped_reason != \"wave complete\"" in FARM
    assert "self._disarm" in FARM
    assert "automatic retry" not in FARM.lower() or "не будет повторять" in FARM.lower()


def test_return_buffer_survives_restart_through_v2_action_journal() -> None:
    assert 'item.request_id.startswith("farm-")' in CONTROLLER
    assert 'runtime.v2_setting("farm_return_buffer_minutes", 5)' in CONTROLLER
    assert "item.return_at" in CONTROLLER
    assert "datetime.now(timezone.utc) < ready_deadline" in CONTROLLER
    assert "FarmState.WAITING_RETURN" in CONTROLLER


def test_scheduler_has_no_direct_spy_browser_or_sql_surface() -> None:
    for forbidden in (
        "request_spy",
        "delete_messages",
        "BrowserWorker",
        "playwright",
        "#SendFleetButton",
        "ajax_fleets.php",
        "sqlite3",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ):
        assert forbidden not in FARM
