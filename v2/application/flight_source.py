from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class FlightSourceStatus:
    available: bool
    detail: str


@dataclass(frozen=True)
class ActiveFlightSnapshot:
    source: str
    target: str
    mission: str
    departure_at: str | None = None
    arrival_at: str | None = None
    return_at: str | None = None
    fleet_id: str | None = None


class FlightSource(Protocol):
    """Narrow read-only contract for live flight data."""

    def status(self) -> FlightSourceStatus: ...

    def flights(self) -> Sequence[ActiveFlightSnapshot]: ...


class OfflineFlightSource:
    """Default V2 source until an explicit browser read service is connected."""

    def status(self) -> FlightSourceStatus:
        return FlightSourceStatus(False, "Live browser source is not connected")

    def flights(self) -> Sequence[ActiveFlightSnapshot]:
        return ()
