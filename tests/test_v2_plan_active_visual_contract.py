from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = (ROOT / "v2" / "ui" / "pages" / "plan.py").read_text(encoding="utf-8")
ACTIVE = (ROOT / "v2" / "ui" / "pages" / "active.py").read_text(encoding="utf-8")
TABLES = (ROOT / "v2" / "ui" / "pages" / "read_tables.py").read_text(encoding="utf-8")


def test_plan_separates_policy_prepare_and_remote_send_visually() -> None:
    assert "Сборка V2-очереди" in PLAN
    assert "Контролируемая отправка" in PLAN
    assert 'tone="warning"' in PLAN
    assert "self.context.prepare_raid" in PLAN
    assert "self.context.dispatch_plan_raid" in PLAN
    assert "одна попытка SendFleet" in PLAN
    assert "НЕ повторит" in PLAN
    assert "QMessageBox.question" in PLAN


def test_active_keeps_explicit_live_refresh_and_reconciliation() -> None:
    assert "StateBanner" in ACTIVE
    assert "Live control" in ACTIVE
    assert "self.context.refresh_live_source()" in ACTIVE
    assert "self.context.classified_active_flights()" in ACTIVE
    assert "self.context.fleet_capacity()" in ACTIVE
    assert "self.context.reconcile_raid_actions()" in ACTIVE
    assert "self.context.recent_raid_actions(limit=200)" in ACTIVE


def test_read_only_tables_have_semantic_alignment_and_horizontal_scroll() -> None:
    assert "TextAlignmentRole" in TABLES
    assert "ScrollBarAsNeeded" in TABLES
    assert "ScrollPerPixel" in TABLES
    assert "NoEditTriggers" in TABLES
    assert 'SIZES["table_row"]' in TABLES


def test_visual_stage_does_not_add_browser_navigation_primitives() -> None:
    combined = PLAN + ACTIVE + TABLES
    for forbidden in (
        "from browser import",
        "import browser",
        "playwright",
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "change_planet.php",
        "launch_yandex(",
    ):
        assert forbidden not in combined
