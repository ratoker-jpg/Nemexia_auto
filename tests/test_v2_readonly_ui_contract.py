from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
TABLES = (ROOT / "v2" / "ui" / "pages" / "read_tables.py").read_text(encoding="utf-8")
RECON = (ROOT / "v2" / "ui" / "pages" / "recon.py").read_text(encoding="utf-8")


def test_qt_preview_bootstraps_through_isolated_v2_and_readonly_legacy_context() -> None:
    assert "build_context(paths)" in APP_QT
    assert "V2Database(paths.database)" in APP_QT
    assert "LegacySettingsImporter" in APP_QT
    assert "ReconOwnedApplicationContext(" in APP_QT
    assert "V2ApplicationContext" in APP_QT
    assert "v2_settings=settings" in APP_QT
    assert "v2_database=database" in APP_QT
    assert "v2_recon=recon" in APP_QT
    assert "V2SpyCdpBackend" in APP_QT
    assert "V2BrowserFlightSource" in APP_QT
    assert "context.close()" in APP_QT
    assert "run_qt_app(paths, context)" in APP_QT


def test_targets_and_history_are_real_context_backed_pages() -> None:
    assert 'if key == "targets"' in MAIN
    assert "TargetsPage(self.context" in MAIN
    assert 'if key == "history"' in MAIN
    assert "HistoryPage(self.context" in MAIN
    assert "context.targets()" in TABLES
    assert "context.history()" in TABLES


def test_read_only_tables_have_no_game_side_effect_or_legacy_storage_writes() -> None:
    forbidden = (
        "send_raid",
        "BrowserWorker",
        "UPDATE targets",
        "DELETE FROM targets",
        "set_setting",
        "replace_queue",
    )
    combined = MAIN + TABLES + RECON
    for token in forbidden:
        assert token not in combined


def test_recon_ui_ingests_through_typed_context_not_direct_sql() -> None:
    assert "ingest_live_recon" in RECON
    assert "context.recon()" in RECON
    assert "sqlite3" not in RECON
    assert "INSERT INTO" not in RECON
    assert "UPDATE " not in RECON


def test_read_only_tables_disable_editing() -> None:
    assert "NoEditTriggers" in TABLES
    assert "QSortFilterProxyModel" in TABLES
    assert "setFilterKeyColumn(-1)" in TABLES
