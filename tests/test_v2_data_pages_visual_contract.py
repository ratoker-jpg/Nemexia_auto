from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECON = (ROOT / "v2" / "ui" / "pages" / "recon.py").read_text(encoding="utf-8")
TABLES = (ROOT / "v2" / "ui" / "pages" / "read_tables.py").read_text(encoding="utf-8")


def test_recon_visually_separates_ingest_from_remote_actions() -> None:
    assert "Recon command" in RECON
    assert 'tone="primary"' in RECON
    assert RECON.count('tone="warning"') >= 2
    assert "StateBanner" in RECON
    assert "EXACT SPY FLEET ID" in RECON
    assert "Принять свежие отчёты" in RECON


def test_recon_keeps_exact_one_shot_mutation_contracts() -> None:
    for token in (
        'getattr(self.context, "ingest_live_recon", None)',
        'getattr(self.context, "prepare_spy", None)',
        'getattr(self.context, "process_spy", None)',
        'getattr(self.context, "run_controlled_recon_refill", None)',
        "ровно одна попытка processSpy",
        "повтор запрещён",
        "QMessageBox.question",
    ):
        assert token in RECON


def test_targets_history_use_read_only_scope_and_empty_states() -> None:
    for token in (
        "EmptyState",
        "V2-owned цели",
        "История подтверждённых и остановленных операций",
        "CRUD и browser discovery в этом visual batch не добавляются",
        "NoEditTriggers",
    ):
        assert token in TABLES


def test_data_pages_do_not_add_navigation_or_direct_browser_capability() -> None:
    combined = RECON + TABLES
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
    ):
        assert forbidden not in combined
