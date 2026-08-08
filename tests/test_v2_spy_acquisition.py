from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2.domain.recon import SpyReportFact
from v2.infrastructure.cdp_spy_backend import select_verified_report


def _report(report_id: str, target: str, at: datetime) -> SpyReportFact:
    return SpyReportFact(report_id=report_id, target=target, reported_at=at, minerals=500_000)


def test_verification_requires_new_exact_target_fresh_report() -> None:
    requested = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    reports = (
        _report("old", "2:22:19", requested + timedelta(seconds=5)),
        _report("wrong-target", "2:22:20", requested + timedelta(seconds=5)),
        _report("stale-new", "2:22:19", requested - timedelta(minutes=5)),
        _report("verified", "2:22:19", requested + timedelta(seconds=8)),
    )
    selected = select_verified_report(reports, before_ids=frozenset({"old"}), target="2:22:19", requested_at=requested)
    assert selected is not None and selected.report_id == "verified"


def test_verification_returns_none_for_ambiguous_evidence() -> None:
    requested = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    assert select_verified_report(
        (_report("old", "2:22:19", requested),), before_ids=frozenset({"old"}),
        target="2:22:19", requested_at=requested,
    ) is None


def test_spy_backend_has_one_mutation_call_and_no_navigation_or_message_deletion() -> None:
    source = (Path(__file__).resolve().parents[1] / "v2/infrastructure/cdp_spy_backend.py").read_text(encoding="utf-8")
    assert source.count("window.processSpy(Number(fleetId))") == 1
    assert "spy1Link-${fleetId}" in source
    assert "link.closest('tr')" in source
    assert "fleetType" in source
    assert "tr.espionageClass" not in source
    assert "loadTabContent('TabAdministrative', 2, 0)" in source
    for forbidden in (
        ".goto(", "new_page(", "bring_to_front(", ".click(", ".fill(",
        "deleteSelectedMessages", "deleteAllMessages", "BrowserWorker", "processSpy(0)",
    ):
        assert forbidden not in source


def test_saved_fleets_fixture_proves_exact_and_bulk_process_spy_modes() -> None:
    html = (Path(__file__).resolve().parents[1] / "saved_pages/2026-08-08_08-54-11-072/page.html").read_text(encoding="utf-8")
    assert 'class="espionageClass"' in html
    assert 'id="spy1Link-152272"' in html
    assert 'onclick="processSpy(152272)"' in html
    assert 'onclick="processSpy(0);" value="Получить все шпионские отчеты"' in html
    assert '>3:39:11</a>' in html
    assert '>2:22:19</a>' in html


def test_recon_ui_is_manual_and_requires_confirmation() -> None:
    source = (Path(__file__).resolve().parents[1] / "v2/ui/pages/recon.py").read_text(encoding="utf-8")
    assert "ProcessSpyButton" in source
    assert "QMessageBox.question" in source
    assert "request_id = f\"spy-" in source
    assert "process(facts.fleet_id, request_id=request_id)" in source
    assert "QTimer" not in source
