from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
RECON = (ROOT / "v2" / "ui" / "pages" / "recon.py").read_text(encoding="utf-8")
REPO = (ROOT / "v2" / "application" / "recon_repository.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2" / "application" / "recon_context.py").read_text(encoding="utf-8")
DATABASE = (ROOT / "v2" / "persistence" / "database.py").read_text(encoding="utf-8")


def test_recon_page_replaces_placeholder() -> None:
    assert 'if key == "recon"' in MAIN
    assert "ReconPage(self.context" in MAIN
    assert "context.recon()" in RECON


def test_recon_surface_reads_v2_owned_typed_storage() -> None:
    assert "ingest_live_recon" in RECON
    assert "V2ReconRepository" in CONTEXT
    assert "recon_reports" in DATABASE
    assert "recon_targets" in DATABASE
    assert '"report_id"' in REPO
    assert '"report_at"' in REPO
    assert '"target"' in REPO
    assert "FROM spy_reports" not in REPO + CONTEXT + RECON


def test_recon_ingestion_keeps_game_mutation_outside_storage_layer() -> None:
    combined = REPO + CONTEXT + DATABASE
    for forbidden in (
        "BrowserWorker",
        "processSpy(",
        "deleteSelectedMessages",
        "deleteAllMessages",
        ".goto(",
        ".click(",
    ):
        assert forbidden not in combined


def test_recon_ui_exposes_report_provenance() -> None:
    assert '"Report ID"' in RECON
    assert "item.report_id" in RECON
    assert "item.report_at" in RECON
    assert "item.target_coord" in RECON
    assert "item.source" in RECON


def test_recon_ui_uses_auto07_without_manual_fleet_id_or_direct_browser_logic() -> None:
    assert "ReconRefillState" in RECON
    assert 'getattr(self.context, "run_automatic_recon", None)' in RECON
    assert 'getattr(self.context, "run_automatic_recon_refill", None)' in RECON
    assert "auto-recon-" in RECON
    assert "recon-refill-" in RECON
    assert "Получить свежий отчёт" in RECON
    assert "Авторазведка → AutoFarm refill" in RECON
    assert "QLineEdit" not in RECON
    assert "SpyFleetId" not in RECON
    assert "EXACT SPY FLEET ID" not in RECON
    assert "run_controlled_recon_refill" not in RECON
    for forbidden in (
        "playwright",
        "BrowserWorker",
        "ajax_fleets.php",
        "sqlite3",
        "processSpy(",
        "#spy1Link-",
        "#spy1Time-",
    ):
        assert forbidden not in RECON
