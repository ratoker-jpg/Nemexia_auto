from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from v2.application.flight_source import FleetCapacitySnapshot, FlightSourceStatus
from v2.application.live_flight_semantics import ClassifiedActiveFlight
from v2.domain.flights import FlightDirection, FlightOwnerScope


DEFAULT_RETURN_BUFFER_MINUTES = 5
MAX_RETURN_BUFFER_MINUTES = 60


@dataclass(frozen=True)
class LiveOverviewSnapshot:
    checked: bool
    available: bool
    detail: str
    active_count: int = 0
    personal_outgoing_count: int = 0
    excluded_count: int = 0
    farm_blocking_count: int = 0
    capacity: FleetCapacitySnapshot | None = None
    latest_farm_return_at: str | None = None
    return_buffer_minutes: int = DEFAULT_RETURN_BUFFER_MINUTES
    inferred_farm_ready_at: str | None = None
    persisted_farm_ready_at: str | None = None
    effective_farm_ready_at: str | None = None


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat() if value else None


def _buffer_minutes(value: object) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = DEFAULT_RETURN_BUFFER_MINUTES
    return max(0, min(MAX_RETURN_BUFFER_MINUTES, parsed))


def build_live_overview(
    *,
    checked: bool,
    status: FlightSourceStatus | None,
    flights: Iterable[ClassifiedActiveFlight],
    capacity: FleetCapacitySnapshot | None,
    return_buffer_minutes: object = DEFAULT_RETURN_BUFFER_MINUTES,
    persisted_farm_ready_at: object = None,
) -> LiveOverviewSnapshot:
    """Summarize already-read live facts without performing browser I/O."""

    if not checked:
        return LiveOverviewSnapshot(
            checked=False,
            available=False,
            detail="Live-данные ещё не проверены",
            return_buffer_minutes=_buffer_minutes(return_buffer_minutes),
            persisted_farm_ready_at=_iso(_parse_dt(persisted_farm_ready_at)),
        )

    if status is None or not status.available:
        return LiveOverviewSnapshot(
            checked=True,
            available=False,
            detail=(status.detail if status else "Live-источник недоступен"),
            return_buffer_minutes=_buffer_minutes(return_buffer_minutes),
            persisted_farm_ready_at=_iso(_parse_dt(persisted_farm_ready_at)),
        )

    items = tuple(flights)
    buffer = _buffer_minutes(return_buffer_minutes)
    personal_outgoing = tuple(
        item
        for item in items
        if not item.facts.excluded
        and item.facts.owner_scope is FlightOwnerScope.PERSONAL
        and item.facts.direction is FlightDirection.OUTGOING
    )
    blocking = tuple(item for item in items if item.facts.blocks_farm_cycle)
    returns = tuple(
        parsed
        for parsed in (_parse_dt(item.raw.return_at) for item in blocking)
        if parsed is not None
    )
    latest_return = max(returns, default=None)
    inferred_ready = latest_return + timedelta(minutes=buffer) if latest_return else None
    persisted_ready = _parse_dt(persisted_farm_ready_at)
    candidates = tuple(item for item in (inferred_ready, persisted_ready) if item is not None)
    effective_ready = max(candidates, default=None)

    return LiveOverviewSnapshot(
        checked=True,
        available=True,
        detail=status.detail,
        active_count=len(items),
        personal_outgoing_count=len(personal_outgoing),
        excluded_count=sum(1 for item in items if item.facts.excluded),
        farm_blocking_count=len(blocking),
        capacity=capacity,
        latest_farm_return_at=_iso(latest_return),
        return_buffer_minutes=buffer,
        inferred_farm_ready_at=_iso(inferred_ready),
        persisted_farm_ready_at=_iso(persisted_ready),
        effective_farm_ready_at=_iso(effective_ready),
    )
