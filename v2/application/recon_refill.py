from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

from v2.application.farm_controller import FarmState
from v2.application.recon_repository import ReconIngestResult
from v2.application.report_source import ReconReadSnapshot
from v2.application.spy_actions import (
    SpyActionsDisabled,
    SpyCaptchaBlocked,
    SpyRequestRejected,
    SpyRequestResult,
)
from v2.application.spy_journal import SpyRequestBlocked
from v2.domain.queue_policy import QueueRefillPreview
from v2.domain.recon import (
    LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES,
    ReportReadState,
    SpyReportFact,
    as_utc,
)
from v2.persistence.queue_refill import QueueApplySummary


class ReconRefillState(str, Enum):
    REFILLED = "refilled"
    EMPTY_COOLDOWN = "empty_cooldown"
    COOLDOWN = "cooldown"
    STOPPED = "stopped"


class ReconRefillStopReason(str, Enum):
    NOT_NEEDED = "not_needed"
    ACTIONS_DISABLED = "actions_disabled"
    LIVE_NOT_CHECKED = "live_not_checked"
    LIVE_UNAVAILABLE = "live_unavailable"
    BLOCKED_UNRESOLVED = "blocked_unresolved"
    CAPTCHA = "captcha"
    SPY_BLOCKED = "spy_blocked"
    SPY_REJECTED = "spy_rejected"
    SPY_AMBIGUOUS = "spy_ambiguous"
    NO_FRESH_REPORT = "no_fresh_report"
    VERIFIED_REPORT_MISSING = "verified_report_missing"
    INGEST_FAILED = "ingest_failed"
    REFILL_FAILED = "refill_failed"


@dataclass(frozen=True)
class ReconRefillResult:
    state: ReconRefillState
    detail: str
    stop_reason: ReconRefillStopReason | None = None
    request_id: str | None = None
    fleet_id: str | None = None
    target: str | None = None
    report_id: str | None = None
    cooldown_until: str | None = None
    ingested: int = 0
    queue_added: int = 0
    queue_kept: int = 0


class ReconRefillRuntime(Protocol):
    def farm_snapshot(self): ...
    def process_spy(self, fleet_id: str, *, request_id: str) -> SpyRequestResult: ...
    def run_automatic_recon(self, *, request_id: str) -> SpyRequestResult: ...
    def live_recon(self, *, now: datetime | None = None, lookback_hours: int = 24) -> ReconReadSnapshot: ...
    def ingest_verified_recon_report(self, report: SpyReportFact, *, now: datetime | None = None) -> ReconIngestResult: ...
    def preview_queue_refill(self, *, mode: str, queue_size: int = 45, now: datetime | None = None): ...
    def apply_queue_refill(self, preview: QueueRefillPreview) -> QueueApplySummary: ...
    def v2_setting(self, key: str, default: object = None) -> object: ...
    def set_v2_setting(self, key: str, value: object) -> object: ...


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _stop_reason_for_farm_state(state: FarmState) -> ReconRefillStopReason:
    return {
        FarmState.ACTIONS_DISABLED: ReconRefillStopReason.ACTIONS_DISABLED,
        FarmState.LIVE_NOT_CHECKED: ReconRefillStopReason.LIVE_NOT_CHECKED,
        FarmState.LIVE_UNAVAILABLE: ReconRefillStopReason.LIVE_UNAVAILABLE,
        FarmState.BLOCKED_UNRESOLVED: ReconRefillStopReason.BLOCKED_UNRESOLVED,
    }.get(state, ReconRefillStopReason.NOT_NEEDED)


def _exact_verified_report(snapshot: ReconReadSnapshot, result: SpyRequestResult) -> SpyReportFact | None:
    if not result.verified or not result.report_id or result.report_at is None:
        return None
    matches = [
        report
        for report in snapshot.fresh_reports
        if report.report_id == result.report_id
        and report.target == result.target
        and report.reported_at is not None
        and as_utc(report.reported_at) == as_utc(result.report_at)
    ]
    return matches[0] if len(matches) == 1 else None


class ControlledReconRefill:
    """Run one verified reconnaissance → V2 ingest → AutoFarm refill cycle.

    With ``fleet_id`` the legacy-compatible manual exact-fleet boundary is used.
    With ``fleet_id=None`` AUTO-07 discovers one processable exact fleet from live
    DOM and still performs at most one journaled ``processSpy(fleet_id)`` attempt.
    This controller never retries a spy mutation and is not a background scheduler.
    """

    COOLDOWN_SETTING = "farm_no_target_cooldown_until"

    def run(
        self,
        runtime: ReconRefillRuntime,
        *,
        fleet_id: str | None,
        request_id: str,
        now: datetime | None = None,
        queue_size: int = 45,
    ) -> ReconRefillResult:
        current = as_utc(now or datetime.now(timezone.utc))
        fleet_label = None if fleet_id is None else str(fleet_id)
        farm = runtime.farm_snapshot()
        if farm.state is not FarmState.NEED_RECON:
            reason = _stop_reason_for_farm_state(farm.state)
            return ReconRefillResult(
                ReconRefillState.STOPPED,
                farm.detail,
                stop_reason=reason,
                request_id=request_id,
                fleet_id=fleet_label,
            )

        cooldown = _parse_utc(runtime.v2_setting(self.COOLDOWN_SETTING, ""))
        if cooldown is not None and current < cooldown:
            return ReconRefillResult(
                ReconRefillState.COOLDOWN,
                f"Успешный пустой scan уже зафиксирован; новая разведка не раньше {_iso(cooldown)}.",
                request_id=request_id,
                fleet_id=fleet_label,
                cooldown_until=_iso(cooldown),
            )

        try:
            if fleet_id is None:
                spy = runtime.run_automatic_recon(request_id=request_id)
            else:
                spy = runtime.process_spy(str(fleet_id), request_id=request_id)
        except SpyCaptchaBlocked as exc:
            return self._stopped(request_id, fleet_label, ReconRefillStopReason.CAPTCHA, str(exc))
        except SpyActionsDisabled as exc:
            return self._stopped(request_id, fleet_label, ReconRefillStopReason.ACTIONS_DISABLED, str(exc))
        except SpyRequestBlocked as exc:
            return self._stopped(request_id, fleet_label, ReconRefillStopReason.SPY_BLOCKED, str(exc))
        except SpyRequestRejected as exc:
            return self._stopped(request_id, fleet_label, ReconRefillStopReason.SPY_REJECTED, str(exc))
        except Exception as exc:
            # Exact intent is already journaled by the selected mutation boundary;
            # after uncertainty the remote action must never be retried here.
            return self._stopped(request_id, fleet_label, ReconRefillStopReason.SPY_AMBIGUOUS, str(exc))

        fleet_label = str(spy.fleet_id)
        if not spy.verified:
            return self._stopped(
                request_id,
                fleet_label,
                ReconRefillStopReason.SPY_AMBIGUOUS,
                spy.detail or "Spy action не подтверждён; автоматический повтор запрещён.",
                target=spy.target,
                report_id=spy.report_id,
            )

        snapshot = runtime.live_recon(now=current)
        if snapshot.state is ReportReadState.CAPTCHA:
            return self._stopped(
                request_id, fleet_label, ReconRefillStopReason.CAPTCHA, snapshot.detail,
                target=spy.target, report_id=spy.report_id,
            )
        if snapshot.state is ReportReadState.LIVE_UNAVAILABLE:
            return self._stopped(
                request_id, fleet_label, ReconRefillStopReason.LIVE_UNAVAILABLE, snapshot.detail,
                target=spy.target, report_id=spy.report_id,
            )
        if snapshot.state is not ReportReadState.FRESH:
            return self._stopped(
                request_id,
                fleet_label,
                ReconRefillStopReason.NO_FRESH_REPORT,
                snapshot.detail or "После подтверждённого spy action нет fresh report evidence.",
                target=spy.target,
                report_id=spy.report_id,
            )

        verified_report = _exact_verified_report(snapshot, spy)
        if verified_report is None:
            return self._stopped(
                request_id,
                fleet_label,
                ReconRefillStopReason.VERIFIED_REPORT_MISSING,
                "Новый fresh report не совпал одновременно по report_id, target и timestamp; refill остановлен.",
                target=spy.target,
                report_id=spy.report_id,
            )

        try:
            ingest = runtime.ingest_verified_recon_report(verified_report, now=current)
        except Exception as exc:
            return self._stopped(
                request_id, fleet_label, ReconRefillStopReason.INGEST_FAILED, str(exc),
                target=spy.target, report_id=spy.report_id,
            )
        if ingest.accepted <= 0:
            return self._stopped(
                request_id,
                fleet_label,
                ReconRefillStopReason.INGEST_FAILED,
                "Verified report не был принят V2 recon repository.",
                target=spy.target,
                report_id=spy.report_id,
            )

        try:
            preview = runtime.preview_queue_refill(
                mode="autofarm",
                queue_size=max(1, int(queue_size)),
                now=current,
            )
        except Exception as exc:
            return self._stopped(
                request_id, fleet_label, ReconRefillStopReason.REFILL_FAILED, str(exc),
                target=spy.target, report_id=spy.report_id,
            )

        if not preview.desired:
            cooldown_until = current + timedelta(minutes=LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES)
            runtime.set_v2_setting(self.COOLDOWN_SETTING, _iso(cooldown_until))
            return ReconRefillResult(
                ReconRefillState.EMPTY_COOLDOWN,
                f"Fresh scan подтверждён, eligible AutoFarm targets = 0; cooldown {LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES} мин.",
                request_id=request_id,
                fleet_id=fleet_label,
                target=spy.target,
                report_id=spy.report_id,
                cooldown_until=_iso(cooldown_until),
                ingested=ingest.accepted,
            )

        try:
            runtime.apply_queue_refill(preview)
            runtime.set_v2_setting(self.COOLDOWN_SETTING, "")
        except Exception as exc:
            return self._stopped(
                request_id, fleet_label, ReconRefillStopReason.REFILL_FAILED, str(exc),
                target=spy.target, report_id=spy.report_id,
            )
        return ReconRefillResult(
            ReconRefillState.REFILLED,
            f"Fresh report подтверждён и очередь AutoFarm пополнена: добавлено {len(preview.added)}, сохранено {len(preview.kept)}.",
            request_id=request_id,
            fleet_id=fleet_label,
            target=spy.target,
            report_id=spy.report_id,
            ingested=ingest.accepted,
            queue_added=len(preview.added),
            queue_kept=len(preview.kept),
        )

    @staticmethod
    def _stopped(
        request_id: str,
        fleet_id: object | None,
        reason: ReconRefillStopReason,
        detail: str,
        *,
        target: str | None = None,
        report_id: str | None = None,
    ) -> ReconRefillResult:
        return ReconRefillResult(
            ReconRefillState.STOPPED,
            str(detail or reason.value),
            stop_reason=reason,
            request_id=request_id,
            fleet_id=None if fleet_id is None else str(fleet_id),
            target=target,
            report_id=report_id,
        )
