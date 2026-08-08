from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from v2.application.flight_source import ActiveFlightSnapshot, FlightSourceStatus


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


class BrowserReadBackend(Protocol):
    """Read-only browser contract used by V2.

    Implementations may inspect an existing browser/CDP session, but this contract
    intentionally exposes no navigation, message deletion, queue mutation or fleet
    dispatch operations.
    """

    def status(self) -> BrowserReadStatus: ...

    def flights(self) -> Sequence[BrowserFlightRecord]: ...


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
