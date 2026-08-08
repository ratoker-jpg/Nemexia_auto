from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FARM = (ROOT / "v2" / "ui" / "pages" / "farm.py").read_text(encoding="utf-8")
CONTROLLER = (ROOT / "v2" / "application" / "farm_controller.py").read_text(encoding="utf-8")


def test_scheduler_is_explicitly_armed_and_session_recon_id_is_never_persisted() -> None:
    assert "QTimer" in FARM
    assert "SCHEDULER_INTERVAL_MS = 30_000" in FARM
    assert "self._armed = False" in FARM
    assert "def start_cycle" in FARM
    assert "QMessageBox.question" in FARM
    assert "self._timer.start()" in FARM
    assert "self._timer.stop()" in FARM
    assert "после перезапуска всегда выключен" in FARM
    assert "FarmSpyFleetId" in FARM
    assert "Spy fleet ID тоже не сохраняется" in FARM
    for forbidden in (
        "farm_auto_enabled",
        "scheduler_enabled",
        "set_v2_setting",
        "set_v2_settings",
        "farm_spy_fleet_id",
    ):
        assert forbidden not in FARM


def test_scheduler_recovers_need_recon_only_through_typed_exact_fleet_boundary() -> None:
    assert "FarmState.NEED_RECON" in FARM
    assert "run_controlled_recon_refill" in FARM
    assert 'request_id=f"recon-cycle-{uuid.uuid4().hex}"' in FARM
    assert "ReconRefillState.REFILLED" in FARM
    assert "ReconRefillState.EMPTY_COOLDOWN" in FARM
    assert "ReconRefillState.COOLDOWN" in FARM
    assert "prepare_spy(fleet_id)" not in FARM  # callable is resolved through context, never browser code
    assert "spy = prepare(fleet_id)" in FARM


def test_scheduler_hard_stops_on_uncertainty_or_live_failure() -> None:
    assert "FarmState.BLOCKED_UNRESOLVED" in FARM
    assert "FarmState.LIVE_UNAVAILABLE" in FARM
    assert "result.stopped_reason != \"wave complete\"" in FARM
    assert "self._disarm" in FARM
    assert "safety-stop recon" in FARM
    assert "без повтора" in FARM


def test_return_buffer_survives_restart_through_v2_action_journal() -> None:
    assert 'item.request_id.startswith("farm-")' in CONTROLLER
    assert 'runtime.v2_setting("farm_return_buffer_minutes", 5)' in CONTROLLER
    assert "item.return_at" in CONTROLLER
    assert "datetime.now(timezone.utc) < ready_deadline" in CONTROLLER
    assert "FarmState.WAITING_RETURN" in CONTROLLER


def test_pending_or_ambiguous_spy_journal_blocks_farm_globally() -> None:
    assert "recent_spy_actions" in CONTROLLER
    assert "unresolved_spy" in CONTROLLER
    assert 'in {"pending", "ambiguous"}' in CONTROLLER
    assert "raid={len(unresolved_raid)}, spy={len(unresolved_spy)}" in CONTROLLER


def test_scheduler_has_no_direct_spy_browser_or_sql_surface() -> None:
    for forbidden in (
        "processSpy(",
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
