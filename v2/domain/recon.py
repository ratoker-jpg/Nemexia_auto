from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Sequence


LEGACY_GAME_SERVER_UTC_OFFSET_HOURS = 4
LEGACY_SPY_REPORT_LOOKBACK_HOURS = 24
LEGACY_METAL_QUEUE_MINIMUM = 480_000
LEGACY_AUTOFARM_MINERALS_MINIMUM = 500_000
LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES = 25

QueueResource = Literal["metal", "minerals"]


class ReconCycleState(str, Enum):
    """Typed outcome of one reconnaissance-read decision.

    V2-41 deliberately models observation only. It does not request spies,
    delete messages, navigate the browser, or mutate either database.
    """

    LIVE_UNAVAILABLE = "live_unavailable"
    CAPTCHA = "captcha"
    NO_FRESH_REPORTS = "no_fresh_reports"
    FRESH_ZERO_ELIGIBLE = "fresh_zero_eligible"
    READY = "ready"


@dataclass(frozen=True)
class SpyReportFact:
    """Smallest report fact set needed by the next V2 reconnaissance stages."""

    report_id: str | None
    target: str
    reported_at: datetime | None
    energy: int | None = None
    metal: int | None = None
    minerals: int | None = None
    gas: int | None = None
    source: str = "messages"

    @property
    def has_verifiable_identity(self) -> bool:
        return bool(self.report_id and self.target and self.reported_at is not None)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def server_wall_clock_to_utc(value: datetime) -> datetime:
    """Preserve the effective legacy Nemexia UTC+04 timestamp interpretation."""

    server_tz = timezone(timedelta(hours=LEGACY_GAME_SERVER_UTC_OFFSET_HOURS))
    wall_clock = value.replace(tzinfo=None)
    return wall_clock.replace(tzinfo=server_tz).astimezone(timezone.utc)


def report_is_fresh(
    report: SpyReportFact,
    *,
    now: datetime,
    lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
) -> bool:
    """Preserve the effective legacy freshness window without inventing time."""

    if report.reported_at is None:
        return False
    hours = max(1, int(lookback_hours))
    return as_utc(report.reported_at) >= as_utc(now) - timedelta(hours=hours)


def eligible_for_manual_queue(
    report: SpyReportFact,
    resource: QueueResource,
    *,
    minimum_metal: int = LEGACY_METAL_QUEUE_MINIMUM,
) -> bool:
    """Mirror the accepted legacy metal/mineral queue resource predicates.

    Enabled/blacklisted/active-target filtering belongs to the target policy,
    not to this report-only fact predicate.
    """

    if resource == "metal":
        return report.metal is not None and int(report.metal) >= max(0, int(minimum_metal))
    if resource == "minerals":
        return report.minerals is not None
    raise ValueError(f"Unsupported queue resource: {resource}")


def eligible_for_legacy_autofarm(report: SpyReportFact) -> bool:
    """Legacy AutoFarm 500k accepts reports with minerals >= 500,000."""

    return report.minerals is not None and int(report.minerals) >= LEGACY_AUTOFARM_MINERALS_MINIMUM


def classify_recon_cycle(
    *,
    browser_available: bool,
    captcha_present: bool,
    fresh_reports: Sequence[SpyReportFact],
    eligible_target_count: int,
) -> ReconCycleState:
    """Keep stop/error states distinct from a successful-but-empty scan."""

    if captcha_present:
        return ReconCycleState.CAPTCHA
    if not browser_available:
        return ReconCycleState.LIVE_UNAVAILABLE
    if not fresh_reports:
        return ReconCycleState.NO_FRESH_REPORTS
    if int(eligible_target_count) <= 0:
        return ReconCycleState.FRESH_ZERO_ELIGIBLE
    return ReconCycleState.READY
