from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FARM = (ROOT / "v2" / "ui" / "pages" / "farm.py").read_text(encoding="utf-8")


def test_farm_is_presented_as_an_operational_command_screen() -> None:
    for token in (
        "AutoFarm command",
        "Операции волны",
        "Recon recovery · текущая сессия",
        "Непрерывный цикл",
        "Safety contract",
        "StateBanner",
        "StatusPill",
    ):
        assert token in FARM
    assert 'tone="warning"' in FARM
    assert 'tone="danger"' in FARM


def test_farm_scheduler_and_session_only_contract_are_unchanged() -> None:
    assert "SCHEDULER_INTERVAL_MS = 30_000" in FARM
    assert "self._armed = False" in FARM
    assert "self._timer.timeout.connect(self._scheduler_tick)" in FARM
    assert "self._timer.start()" in FARM
    assert "self._timer.stop()" in FARM
    assert "Цикл и Spy fleet ID НЕ сохраняются после перезапуска" in FARM
    assert "processSpy" in FARM
    assert "без повтора" in FARM


def test_farm_keeps_existing_typed_application_routes() -> None:
    for call in (
        "self.context.farm_snapshot()",
        "self.context.refresh_live_source()",
        "self.context.reconcile_raid_actions()",
        "self.context.run_farm_wave(",
        'getattr(self.context, "prepare_spy", None)',
        'getattr(self.context, "run_controlled_recon_refill", None)',
    ):
        assert call in FARM


def test_farm_ui_still_has_no_direct_browser_sql_or_navigation_surface() -> None:
    for forbidden in (
        "from browser import",
        "import browser",
        "BrowserWorker",
        "playwright",
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "change_planet.php",
        "launch_yandex(",
        "sqlite3",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ):
        assert forbidden not in FARM
