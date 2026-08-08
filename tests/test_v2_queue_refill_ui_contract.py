from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = (ROOT / "v2" / "ui" / "pages" / "plan.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2" / "application" / "recon_context.py").read_text(encoding="utf-8")
POLICY = (ROOT / "v2" / "domain" / "queue_policy.py").read_text(encoding="utf-8")
STORE = (ROOT / "v2" / "persistence" / "queue_refill.py").read_text(encoding="utf-8")


def test_plan_exposes_preview_and_local_apply_without_text_driven_mode() -> None:
    assert 'addItem("Металл", "metal")' in PLAN
    assert 'addItem("Минералы", "minerals")' in PLAN
    assert 'addItem("AutoFarm ≥500k", "autofarm")' in PLAN
    assert "currentData()" in PLAN
    assert "currentText()" not in PLAN
    assert "preview_queue_refill" in PLAN
    assert "apply_queue_refill" in PLAN
    assert "QMessageBox.question" in PLAN


def test_context_uses_only_cached_active_flights_for_preview() -> None:
    assert "preview_queue_refill" in CONTEXT
    assert "self._live_snapshot_ready" in CONTEXT
    assert "self.cached_classified_active_flights()" in CONTEXT
    assert "refresh_live_source()" not in CONTEXT
    assert "BrowserWorker" not in CONTEXT


def test_queue_policy_is_pure_and_storage_has_no_browser_actions() -> None:
    combined = POLICY + STORE
    for forbidden in (
        "playwright", "BrowserWorker", "processSpy(", "SendFleet", "ajax_fleets.php",
        "deleteSelectedMessages", ".goto(", ".click(",
    ):
        assert forbidden not in combined
    assert "build_queue_refill_preview" in POLICY
    assert "PROTECTED_QUEUE_STATES" in POLICY
    assert "BEGIN" not in PLAN
    assert "sqlite3" not in PLAN
