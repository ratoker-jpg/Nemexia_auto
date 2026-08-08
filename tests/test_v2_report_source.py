from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.report_source import (
    BrowserReportStatus,
    BrowserSpyReportSnapshot,
    V2BrowserReportSource,
)
from v2.domain.recon import ReportReadState, SpyReportFact


class FakeReportBackend:
    def __init__(self, snapshot: BrowserSpyReportSnapshot) -> None:
        self.snapshot = snapshot
        self.reads = 0

    def read_spy_reports(self) -> BrowserSpyReportSnapshot:
        self.reads += 1
        return self.snapshot


def _report(report_id: str, target: str, reported_at: datetime | None) -> SpyReportFact:
    return SpyReportFact(
        report_id=report_id,
        target=target,
        reported_at=reported_at,
        metal=600_000,
        minerals=520_000,
    )


def test_report_source_distinguishes_live_unavailable_captcha_and_no_reports() -> None:
    offline = FakeReportBackend(
        BrowserSpyReportSnapshot(BrowserReportStatus(False, detail="options.php is not open"))
    )
    assert V2BrowserReportSource(offline).read().state is ReportReadState.LIVE_UNAVAILABLE
    assert offline.reads == 1

    captcha = FakeReportBackend(
        BrowserSpyReportSnapshot(
            BrowserReportStatus(False, captcha_present=True, detail="CAPTCHA detected")
        )
    )
    assert V2BrowserReportSource(captcha).read().state is ReportReadState.CAPTCHA
    assert captcha.reads == 1

    empty = FakeReportBackend(
        BrowserSpyReportSnapshot(BrowserReportStatus(True, detail="rendered"), ())
    )
    snapshot = V2BrowserReportSource(empty).read()
    assert snapshot.state is ReportReadState.NO_REPORTS
    assert snapshot.available is True
    assert snapshot.reports == ()
    assert empty.reads == 1


def test_report_source_separates_fresh_from_stale_without_mutation() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    fresh = _report("fresh", "3:1:2", datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc))
    stale = _report("stale", "3:1:3", datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc))
    backend = FakeReportBackend(
        BrowserSpyReportSnapshot(BrowserReportStatus(True, detail="rendered"), (fresh, stale))
    )
    snapshot = V2BrowserReportSource(backend).read(now=now)
    assert snapshot.state is ReportReadState.FRESH
    assert snapshot.fresh_reports == (fresh,)
    assert snapshot.stale_reports == (stale,)
    assert backend.reads == 1

    stale_only = FakeReportBackend(
        BrowserSpyReportSnapshot(BrowserReportStatus(True), (stale,))
    )
    assert V2BrowserReportSource(stale_only).read(now=now).state is ReportReadState.STALE_ONLY


def test_context_exposes_typed_live_recon_service(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    report = _report("fresh", "3:1:2", datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc))
    backend = FakeReportBackend(
        BrowserSpyReportSnapshot(BrowserReportStatus(True), (report,))
    )
    context = V2ApplicationContext(
        tmp_path / "missing.sqlite3",
        report_source=V2BrowserReportSource(backend),
    )
    try:
        snapshot = context.live_recon(now=now)
        assert snapshot.state is ReportReadState.FRESH
        assert snapshot.fresh_reports[0].target == "3:1:2"
    finally:
        context.close()


def test_context_without_report_source_fails_closed(tmp_path: Path) -> None:
    context = V2ApplicationContext(tmp_path / "missing.sqlite3")
    try:
        snapshot = context.live_recon()
        assert snapshot.state is ReportReadState.LIVE_UNAVAILABLE
        assert snapshot.available is False
    finally:
        context.close()
