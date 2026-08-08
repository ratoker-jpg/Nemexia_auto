from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from v2.domain.recon import (
    LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ReportReadState,
    SpyReportFact,
    report_is_fresh,
)


@dataclass(frozen=True)
class BrowserReportStatus:
    available: bool
    captcha_present: bool = False
    endpoint: str | None = None
    page_url: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class BrowserSpyReportSnapshot:
    status: BrowserReportStatus
    reports: tuple[SpyReportFact, ...] = ()


@dataclass(frozen=True)
class ReconReadSnapshot:
    state: ReportReadState
    reports: tuple[SpyReportFact, ...]
    fresh_reports: tuple[SpyReportFact, ...]
    stale_reports: tuple[SpyReportFact, ...]
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.state not in {ReportReadState.LIVE_UNAVAILABLE, ReportReadState.CAPTCHA}


class BrowserReportBackend(Protocol):
    """Read-only browser report contract.

    Implementations may inspect already-rendered report DOM only. This boundary
    intentionally exposes no navigation, spy request, message deletion or other
    game mutation.
    """

    def read_spy_reports(self) -> BrowserSpyReportSnapshot: ...


class V2BrowserReportSource:
    """Classify already-observed browser report facts by freshness."""

    def __init__(self, backend: BrowserReportBackend) -> None:
        self._backend = backend

    def read(
        self,
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconReadSnapshot:
        snapshot = self._backend.read_spy_reports()
        status = snapshot.status
        if status.captcha_present:
            return ReconReadSnapshot(
                ReportReadState.CAPTCHA,
                (),
                (),
                (),
                status.detail or "CAPTCHA requires manual attention",
            )
        if not status.available:
            return ReconReadSnapshot(
                ReportReadState.LIVE_UNAVAILABLE,
                (),
                (),
                (),
                status.detail or "Report source is unavailable",
            )

        reports = tuple(snapshot.reports)
        if not reports:
            return ReconReadSnapshot(
                ReportReadState.NO_REPORTS,
                (),
                (),
                (),
                status.detail or "No spy reports are rendered",
            )

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        fresh = tuple(
            report for report in reports
            if report_is_fresh(report, now=current, lookback_hours=lookback_hours)
        )
        stale = tuple(report for report in reports if report not in fresh)
        state = ReportReadState.FRESH if fresh else ReportReadState.STALE_ONLY
        detail = status.detail or (
            f"Fresh reports: {len(fresh)}" if fresh else f"Stale reports only: {len(stale)}"
        )
        return ReconReadSnapshot(state, reports, fresh, stale, detail)
