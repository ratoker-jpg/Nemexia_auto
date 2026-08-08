from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = (ROOT / "v2" / "ui" / "pages" / "plan.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2" / "application" / "context.py").read_text(encoding="utf-8")


def test_plan_dispatch_requires_explicit_confirmation_and_unique_request_id() -> None:
    assert "QMessageBox.question" in PLAN
    assert "StandardButton.Yes" in PLAN
    assert "StandardButton.No" in PLAN
    assert "uuid.uuid4().hex" in PLAN
    assert "dispatch_plan_raid" in PLAN
    assert "одна попытка SendFleet" in PLAN
    assert "НЕ повторит" in PLAN


def test_plan_actions_remain_behind_global_action_gate() -> None:
    assert "raid_actions_enabled()" in PLAN
    assert "Действия V2 выключены" in PLAN
    assert "item.state != \"queued\"" in PLAN
    assert "prepare_raid" in PLAN
    assert "dispatch_plan_raid" in CONTEXT
    assert "RaidDispatchCoordinator" in CONTEXT


def test_plan_ui_has_no_direct_browser_or_sql_mutation() -> None:
    for forbidden in (
        "playwright",
        "#SendFleetButton",
        "ajax_fleets.php",
        "sqlite3",
        "INSERT INTO",
        "UPDATE raid_queue",
        "BrowserWorker",
    ):
        assert forbidden not in PLAN
