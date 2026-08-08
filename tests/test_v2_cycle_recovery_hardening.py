from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2.application.farm_controller import FarmSnapshot, FarmState
from v2.application.recon_refill import ControlledReconRefill, ReconRefillState, ReconRefillStopReason
from v2.application.recon_repository import ReconIngestResult
from v2.application.report_source import ReconReadSnapshot
from v2.application.spy_actions import SpyRequestResult
from v2.application.v2_settings import V2SettingsRepository
from v2.domain.queue_policy import QueueRefillPreview
from v2.domain.recon import ReportReadState, SpyReportFact
from v2.persistence.database import V2Database
from v2.persistence.queue_refill import QueueApplySummary


NOW = datetime(2026, 8, 8, 16, 0, 0, tzinfo=timezone.utc)
REPORT = SpyReportFact(
    report_id="report-recovery-1",
    target="3:12:7",
    reported_at=NOW,
    metal=100_000,
    minerals=750_000,
    gas=20_000,
)


def empty_preview() -> QueueRefillPreview:
    return QueueRefillPreview(
        mode="autofarm",
        queue_size=45,
        desired=(),
        added=(),
        kept=(),
        removed=(),
        protected=(),
        skipped=(),
    )


class Runtime:
    def __init__(self, *, settings: V2SettingsRepository | None = None) -> None:
        self.settings_repo = settings
        self.settings = {"farm_no_target_cooldown_until": ""}
        self.spy_calls: list[tuple[str, str]] = []
        self.live = ReconReadSnapshot(ReportReadState.FRESH, (REPORT,), (REPORT,), (), "fresh")
        self.queue_preview = empty_preview()
        self.ingested: list[SpyReportFact] = []

    def farm_snapshot(self):
        return FarmSnapshot(FarmState.NEED_RECON, "need recon", 0, 5, 0, 0)

    def process_spy(self, fleet_id: str, *, request_id: str):
        self.spy_calls.append((fleet_id, request_id))
        return SpyRequestResult(
            fleet_id=fleet_id,
            source="3:39:11",
            target=REPORT.target,
            requested_at=NOW,
            verified=True,
            report_id=REPORT.report_id,
            report_at=REPORT.reported_at,
            detail="verified",
        )

    def live_recon(self, *, now=None, lookback_hours=24):
        return self.live

    def ingest_verified_recon_report(self, report: SpyReportFact, *, now=None):
        self.ingested.append(report)
        return ReconIngestResult(1, 0, 0, 0)

    def preview_queue_refill(self, *, mode, queue_size=45, now=None):
        assert mode == "autofarm"
        return self.queue_preview

    def apply_queue_refill(self, preview):
        return QueueApplySummary(created=0, updated=0, removed=0)

    def v2_setting(self, key, default=None):
        if self.settings_repo is not None:
            return self.settings_repo.get(key)
        return self.settings.get(key, default)

    def set_v2_setting(self, key, value):
        if self.settings_repo is not None:
            return self.settings_repo.set(key, value)
        self.settings[key] = value
        return value


def test_stale_only_reports_stop_without_starting_empty_result_cooldown() -> None:
    runtime = Runtime()
    stale = SpyReportFact(
        report_id=REPORT.report_id,
        target=REPORT.target,
        reported_at=NOW - timedelta(days=2),
        minerals=900_000,
    )
    runtime.live = ReconReadSnapshot(ReportReadState.STALE_ONLY, (stale,), (), (stale,), "stale only")
    result = ControlledReconRefill().run(runtime, fleet_id="152272", request_id="stale", now=NOW)
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.NO_FRESH_REPORT
    assert runtime.settings["farm_no_target_cooldown_until"] == ""


def test_captcha_during_report_verification_stops_fail_closed() -> None:
    runtime = Runtime()
    runtime.live = ReconReadSnapshot(ReportReadState.CAPTCHA, (), (), (), "captcha")
    result = ControlledReconRefill().run(runtime, fleet_id="152272", request_id="captcha", now=NOW)
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.CAPTCHA
    assert runtime.ingested == []


def test_live_unavailable_during_report_verification_stops_fail_closed() -> None:
    runtime = Runtime()
    runtime.live = ReconReadSnapshot(ReportReadState.LIVE_UNAVAILABLE, (), (), (), "offline")
    result = ControlledReconRefill().run(runtime, fleet_id="152272", request_id="offline", now=NOW)
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.LIVE_UNAVAILABLE
    assert runtime.ingested == []


def test_duplicate_exact_report_evidence_is_not_silently_accepted() -> None:
    runtime = Runtime()
    runtime.live = ReconReadSnapshot(
        ReportReadState.FRESH,
        (REPORT, REPORT),
        (REPORT, REPORT),
        (),
        "duplicate evidence",
    )
    result = ControlledReconRefill().run(runtime, fleet_id="152272", request_id="duplicate", now=NOW)
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.VERIFIED_REPORT_MISSING
    assert runtime.ingested == []


def test_no_target_cooldown_survives_database_restart_and_blocks_new_spy_attempt(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        runtime = Runtime(settings=V2SettingsRepository(db))
        first = ControlledReconRefill().run(
            runtime,
            fleet_id="152272",
            request_id="empty-first",
            now=NOW,
        )
        assert first.state is ReconRefillState.EMPTY_COOLDOWN
        assert first.cooldown_until == "2026-08-08T16:25:00+00:00"
        assert runtime.spy_calls == [("152272", "empty-first")]

    with V2Database(path) as db:
        restarted = Runtime(settings=V2SettingsRepository(db))
        second = ControlledReconRefill().run(
            restarted,
            fleet_id="152272",
            request_id="after-restart",
            now=NOW + timedelta(minutes=5),
        )
        assert second.state is ReconRefillState.COOLDOWN
        assert second.cooldown_until == "2026-08-08T16:25:00+00:00"
        assert restarted.spy_calls == []
