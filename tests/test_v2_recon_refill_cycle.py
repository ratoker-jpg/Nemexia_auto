from __future__ import annotations

from datetime import datetime, timezone

from v2.application.farm_controller import FarmSnapshot, FarmState
from v2.application.recon_refill import (
    ControlledReconRefill,
    ReconRefillState,
    ReconRefillStopReason,
)
from v2.application.recon_repository import ReconIngestResult
from v2.application.report_source import ReconReadSnapshot
from v2.application.spy_actions import SpyRequestResult
from v2.domain.queue_policy import QueueDesiredRow, QueueRefillPreview
from v2.domain.recon import ReportReadState, SpyReportFact
from v2.persistence.queue_refill import QueueApplySummary


NOW = datetime(2026, 8, 8, 16, 0, 0, tzinfo=timezone.utc)
REPORT = SpyReportFact(
    report_id="report-9001",
    target="3:12:7",
    reported_at=NOW,
    metal=200_000,
    minerals=800_000,
    gas=10_000,
)


def farm(state: FarmState = FarmState.NEED_RECON) -> FarmSnapshot:
    return FarmSnapshot(state, state.value, 0, 10, 0, 0)


def preview(*, desired: bool) -> QueueRefillPreview:
    rows = (
        QueueDesiredRow(
            position=1,
            coord=REPORT.target,
            player="Target",
            metal=REPORT.metal,
            minerals=REPORT.minerals,
            gas=REPORT.gas,
            last_spy_at=NOW.isoformat(),
        ),
    ) if desired else ()
    return QueueRefillPreview(
        mode="autofarm",
        queue_size=45,
        desired=rows,
        added=(REPORT.target,) if desired else (),
        kept=(),
        removed=(),
        protected=(),
        skipped=(),
    )


class Runtime:
    def __init__(self) -> None:
        self.farm_state = FarmState.NEED_RECON
        self.spy_result = SpyRequestResult(
            fleet_id="152272",
            source="3:39:11",
            target=REPORT.target,
            requested_at=NOW,
            verified=True,
            report_id=REPORT.report_id,
            report_at=REPORT.reported_at,
            detail="verified",
        )
        self.live = ReconReadSnapshot(
            ReportReadState.FRESH,
            (REPORT,),
            (REPORT,),
            (),
            "fresh",
        )
        self.ingest = ReconIngestResult(1, 0, 0, 0)
        self.queue_preview = preview(desired=True)
        self.settings = {"farm_no_target_cooldown_until": ""}
        self.spy_calls: list[tuple[str, str]] = []
        self.ingested: list[SpyReportFact] = []
        self.preview_calls = 0
        self.apply_calls = 0

    def farm_snapshot(self):
        return farm(self.farm_state)

    def process_spy(self, fleet_id: str, *, request_id: str):
        self.spy_calls.append((fleet_id, request_id))
        return self.spy_result

    def live_recon(self, *, now=None, lookback_hours=24):
        return self.live

    def ingest_verified_recon_report(self, report: SpyReportFact, *, now=None):
        self.ingested.append(report)
        return self.ingest

    def preview_queue_refill(self, *, mode, queue_size=45, now=None):
        assert mode == "autofarm"
        self.preview_calls += 1
        return self.queue_preview

    def apply_queue_refill(self, queue_preview):
        assert queue_preview is self.queue_preview
        self.apply_calls += 1
        return QueueApplySummary(created=len(queue_preview.added), updated=0, removed=0)

    def v2_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_v2_setting(self, key, value):
        self.settings[key] = value
        return value


def test_controlled_cycle_uses_one_verified_spy_then_ingests_exact_report_and_refills() -> None:
    runtime = Runtime()
    result = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-1",
        now=NOW,
    )
    assert result.state is ReconRefillState.REFILLED
    assert result.report_id == REPORT.report_id
    assert result.target == REPORT.target
    assert result.ingested == 1
    assert result.queue_added == 1
    assert runtime.spy_calls == [("152272", "recon-refill-1")]
    assert runtime.ingested == [REPORT]
    assert runtime.preview_calls == 1
    assert runtime.apply_calls == 1
    assert runtime.settings["farm_no_target_cooldown_until"] == ""


def test_fresh_verified_scan_with_zero_autofarm_targets_sets_separate_25_minute_cooldown() -> None:
    runtime = Runtime()
    runtime.queue_preview = preview(desired=False)
    first = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-empty",
        now=NOW,
    )
    assert first.state is ReconRefillState.EMPTY_COOLDOWN
    assert first.cooldown_until == "2026-08-08T16:25:00+00:00"
    assert runtime.settings["farm_no_target_cooldown_until"] == first.cooldown_until
    assert runtime.apply_calls == 0

    second = ControlledReconRefill().run(
        runtime,
        fleet_id="152273",
        request_id="recon-refill-too-early",
        now=NOW,
    )
    assert second.state is ReconRefillState.COOLDOWN
    assert runtime.spy_calls == [("152272", "recon-refill-empty")]


def test_no_fresh_reports_after_verified_action_is_stop_not_empty_cooldown() -> None:
    runtime = Runtime()
    runtime.live = ReconReadSnapshot(
        ReportReadState.NO_REPORTS,
        (),
        (),
        (),
        "no fresh reports",
    )
    result = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-no-report",
        now=NOW,
    )
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.NO_FRESH_REPORT
    assert runtime.settings["farm_no_target_cooldown_until"] == ""
    assert runtime.preview_calls == 0
    assert runtime.apply_calls == 0


def test_verified_report_must_match_exact_id_target_and_timestamp_before_ingest() -> None:
    runtime = Runtime()
    other = SpyReportFact(
        report_id="different-report",
        target=REPORT.target,
        reported_at=NOW,
        minerals=900_000,
    )
    runtime.live = ReconReadSnapshot(ReportReadState.FRESH, (other,), (other,), (), "fresh")
    result = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-mismatch",
        now=NOW,
    )
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.VERIFIED_REPORT_MISSING
    assert runtime.ingested == []
    assert runtime.apply_calls == 0


def test_ambiguous_spy_result_stops_without_refill_or_retry() -> None:
    runtime = Runtime()
    runtime.spy_result = SpyRequestResult(
        fleet_id="152272",
        source="3:39:11",
        target=REPORT.target,
        requested_at=NOW,
        verified=False,
        detail="unverified",
    )
    result = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-ambiguous",
        now=NOW,
    )
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.SPY_AMBIGUOUS
    assert runtime.spy_calls == [("152272", "recon-refill-ambiguous")]
    assert runtime.ingested == []
    assert runtime.preview_calls == 0


def test_non_need_recon_farm_state_stops_before_spy_side_effect() -> None:
    runtime = Runtime()
    runtime.farm_state = FarmState.ACTIONS_DISABLED
    result = ControlledReconRefill().run(
        runtime,
        fleet_id="152272",
        request_id="recon-refill-disabled",
        now=NOW,
    )
    assert result.state is ReconRefillState.STOPPED
    assert result.stop_reason is ReconRefillStopReason.ACTIONS_DISABLED
    assert runtime.spy_calls == []
