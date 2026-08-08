from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
TABLES = (ROOT / "v2" / "ui" / "pages" / "read_tables.py").read_text(encoding="utf-8")


def test_qt_preview_bootstraps_through_read_only_application_context() -> None:
    assert "V2ApplicationContext.auto_detect()" in APP_QT
    assert "context.close()" in APP_QT
    assert "run_qt_app(paths, context)" in APP_QT


def test_targets_and_history_are_real_context_backed_pages() -> None:
    assert 'if key == "targets"' in MAIN
    assert "TargetsPage(self.context" in MAIN
    assert 'if key == "history"' in MAIN
    assert "HistoryPage(self.context" in MAIN
    assert "context.targets()" in TABLES
    assert "context.history()" in TABLES


def test_read_only_pages_have_no_game_or_storage_write_actions() -> None:
    forbidden = (
        "send_raid",
        "BrowserWorker",
        "UPDATE targets",
        "INSERT INTO",
        "DELETE FROM",
        "set_setting",
        "replace_queue",
    )
    combined = MAIN + TABLES
    for token in forbidden:
        assert token not in combined


def test_read_only_tables_disable_editing() -> None:
    assert "NoEditTriggers" in TABLES
    assert "QSortFilterProxyModel" in TABLES
    assert "setFilterKeyColumn(-1)" in TABLES
