from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from v2.application.flight_source import (
    ActiveFlightSnapshot,
    FleetCapacitySnapshot,
    FlightSourceStatus,
)


@dataclass(frozen=True)
class BrowserReadStatus:
    connected: bool
    captcha_present: bool = False
    endpoint: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class BrowserFlightRecord:
    source: str
    target: str
    mission: str
    departure_at: str | None = None
    arrival_at: str | None = None
    return_at: str | None = None
    fleet_id: str | None = None


@dataclass(frozen=True)
class BrowserFleetCapacity:
    used: int
    maximum: int

    @property
    def free(self) -> int:
        return max(0, int(self.maximum) - int(self.used))


class BrowserReadBackend(Protocol):
    """Read-only browser contract used by V2.

    Implementations may inspect an existing browser/CDP session, but this contract
    intentionally exposes no navigation, message deletion, queue mutation or fleet
    dispatch operations. Fleet capacity must come from the game's own counters,
    never from the number of rows returned by ``flights()``.
    """

    def status(self) -> BrowserReadStatus: ...

    def flights(self) -> Sequence[BrowserFlightRecord]: ...

    def capacity(self) -> BrowserFleetCapacity | None: ...


class V2BrowserFlightSource:
    """Adapt neutral browser facts to the V2 `FlightSource` boundary."""

    def __init__(self, backend: BrowserReadBackend) -> None:
        self._backend = backend

    def browser_status(self) -> BrowserReadStatus:
        return self._backend.status()

    def status(self) -> FlightSourceStatus:
        state = self._backend.status()
        if not state.connected:
            return FlightSourceStatus(False, state.detail or "Browser is not connected")
        if state.captcha_present:
            return FlightSourceStatus(False, state.detail or "CAPTCHA requires manual attention")
        return FlightSourceStatus(True, state.detail or "Browser read source is connected")

    def flights(self) -> Sequence[ActiveFlightSnapshot]:
        if not self.status().available:
            return ()
        return tuple(
            ActiveFlightSnapshot(
                source=item.source,
                target=item.target,
                mission=item.mission,
                departure_at=item.departure_at,
                arrival_at=item.arrival_at,
                return_at=item.return_at,
                fleet_id=item.fleet_id,
            )
            for item in self._backend.flights()
        )

    def owned_planets(self) -> tuple[str, ...]:
        reader = getattr(self._backend, "owned_planets", None)
        if not callable(reader):
            return ()
        return tuple(str(coord) for coord in reader())

    def capacity(self) -> FleetCapacitySnapshot | None:
        if not self.status().available:
            return None
        capacity = self._backend.capacity()
        if capacity is None:
            return None
        used = max(0, int(capacity.used))
        maximum = max(0, int(capacity.maximum))
        if maximum <= 0 or used > maximum:
            return None
        return FleetCapacitySnapshot(
            used=used,
            maximum=maximum,
            free=max(0, maximum - used),
            source="game DOM #FleetsCount/#MaxFleets",
        )

    def refresh(self) -> None:
        invalidator = getattr(self._backend, "invalidate", None)
        if callable(invalidator):
            invalidator()

    def close(self) -> None:
        closer = getattr(self._backend, "close", None)
        if callable(closer):
            closer()
