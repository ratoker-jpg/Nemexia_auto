from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from v2.application.live_flight_semantics import ClassifiedActiveFlight
from v2.application.raid_journal import RaidActionRecord, RaidDispatchCoordinator


@dataclass(frozen=True)
class RaidReconciliation:
    request_id: str
    target: str
    fleet_id: str


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reconcile_unresolved_raids(
    coordinator: RaidDispatchCoordinator,
    records: Iterable[RaidActionRecord],
    flights: Iterable[ClassifiedActiveFlight],
) -> list[RaidReconciliation]:
    """Resolve only unambiguous exact live matches; uncertain records stay blocked."""
    live = tuple(flights)
    resolved: list[RaidReconciliation] = []
    for record in records:
        if record.status not in {"pending", "ambiguous"}:
            continue
        basis = _dt(record.sent_at) or _dt(record.created_at)
        candidates: list[ClassifiedActiveFlight] = []
        for flight in live:
            raw = flight.raw
            if str(raw.source) != record.source or str(raw.target) != record.target:
                continue
            if str(raw.mission or "").strip().casefold() != "атака":
                continue
            if not str(raw.fleet_id or "").strip():
                continue
            if record.fleet_id and str(raw.fleet_id) != record.fleet_id:
                continue
            departure = _dt(raw.departure_at)
            if basis is not None and departure is not None and departure < basis:
                continue
            if basis is not None and departure is None and not record.fleet_id:
                continue
            candidates.append(flight)

        # Never guess between multiple same-target attacks.
        if len(candidates) != 1:
            continue
        raw = candidates[0].raw
        record = coordinator.resolve_verified(
            record.request_id,
            fleet_id=str(raw.fleet_id),
            sent_at=raw.departure_at,
            arrival_at=raw.arrival_at,
            return_at=raw.return_at,
        )
        resolved.append(
            RaidReconciliation(
                request_id=record.request_id,
                target=record.target,
                fleet_id=str(record.fleet_id),
            )
        )
    return resolved
