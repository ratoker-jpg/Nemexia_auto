from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FARM = (ROOT / "v2" / "ui" / "pages" / "farm.py").read_text(encoding="utf-8")
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
CONTROLLER = (ROOT / "v2" / "application" / "farm_controller.py").read_text(encoding="utf-8")


def test_farm_placeholder_is_replaced_by_typed_page() -> None:
    assert 'if key == "farm"' in MAIN
    assert "FarmPage(self.context" in MAIN
    assert "context.farm_snapshot()" in FARM
    assert "context.run_farm_wave" in FARM
    assert "QMessageBox.question" in FARM
    assert "Выполнить одну волну" in FARM


def test_farm_controller_uses_typed_states_not_ui_strings() -> None:
    for state in (
        "ACTIONS_DISABLED", "LIVE_NOT_CHECKED", "LIVE_UNAVAILABLE",
        "BLOCKED_UNRESOLVED", "WAITING_RETURN", "WAITING_CAPACITY",
        "NO_TARGETS", "READY",
    ):
        assert state in CONTROLLER
    assert "startswith(" not in CONTROLLER


def test_farm_page_has_no_direct_browser_sql_or_sendfleet_calls() -> None:
    for forbidden in (
        "playwright", "BrowserWorker", "#SendFleetButton", "ajax_fleets.php",
        "sqlite3", "INSERT INTO", "UPDATE ", "DELETE FROM",
    ):
        assert forbidden not in FARM
