from __future__ import annotations

from datetime import datetime, timezone

from v2.application.farm_controller import FarmSnapshot, FarmState
from v2.application.recon_refill import ControlledReconRefill, ReconRefillState
from v2.application.recon_repository import ReconIngestResult
from v2.application.report_source import ReconReadSnapshot
from v2.application.spy_actions import SpyRequestResult
from v2.domain.queue_policy import QueueDesiredRow, QueueRefillPreview
from v2.domain.recon import ReportReadState, SpyReportFact


NOW = datetime(2026, 8, 9, 16, 45, tzinfo=timezone.utc)
REPORT = SpyReportFact(
    report_id="auto-report-1",
    target="2:22:19",
    reported_at=NOW,
    metal=100_000,
    minerals=900_000,
    gas=10_000,
)


class Runtime:
    def __init__(self) -> None:
        self.auto_calls: list[str] = []
        self.manual_calls: list[tuple[str, str]] = []
        self.ingested = 0
        self.applied = 0
        self.settings = {"farm_no_target_cooldown_until": ""}

    def farm_snapshot(self):
        return FarmSnapshot(FarmState.NEED_RECON, "need recon", 0, 10, 0, 0)

    def run_automatic_recon(self, *, request_id: str):
        self.auto_calls.append(request_id)
        return SpyRequestResult(
            fleet_id="152272",
            source="3:39:11",
            target=REPORT.target,
            requested_at=NOW,
            verified=True,
            report_id=REPORT.report_id,
            report_at=REPORT.reported_at,
            detail="verified",
        )

    def process_spy(self, fleet_id: str, *, request_id: str):
        self.manual_calls.append((fleet_id, request_id))
        raise AssertionError("manual exact-fleet path must not run for AUTO-07")

    def live_recon(self, *, now=None, lookback_hours=24):
        return ReconReadSnapshot(ReportReadState.FRESH, (REPORT,), (REPORT,), (), "fresh")

    def ingest_verified_recon_report(self, report: SpyReportFact, *, now=None):
        assert report is REPORT
        self.ingested += 1
        return ReconIngestResult(1, 0, 0, 0)

    def preview_queue_refill(self, *, mode, queue_size=45, now=None):
        desired = QueueDesiredRow(
            position=1,
            coord=REPORT.target,
            player="Target",
            metal=REPORT.metal,
            minerals=REPORT.minerals,
            gas=REPORT.gas,
            last_spy_at=NOW.isoformat(),
        )
        return QueueRefillPreview(
            mode="autofarm",
            queue_size=45,
            desired=(desired,),
            added=(REPORT.target,),
            kept=(),
            removed=(),
            protected=(),
            skipped=(),
        )

    def apply_queue_refill(self, preview):
        self.applied += 1

    def v2_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_v2_setting(self, key, value):
        self.settings[key] = value
        return value


def test_none_fleet_id_uses_automatic_recon_then_existing_verified_refill_pipeline() -> None:
    runtime = Runtime()
    result = ControlledReconRefill().run(
        runtime,
        fleet_id=None,
        request_id="auto-refill-1",
        now=NOW,
    )
    assert result.state is ReconRefillState.REFILLED
    assert result.fleet_id == "152272"
    assert result.report_id == REPORT.report_id
    assert runtime.auto_calls == ["auto-refill-1"]
    assert runtime.manual_calls == []
    assert runtime.ingested == 1
    assert runtime.applied == 1
