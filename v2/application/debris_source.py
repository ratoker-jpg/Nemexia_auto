from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from v2.domain.debris import DebrisObservationFact, DebrisReadState, classify_debris_read_state


@dataclass(frozen=True)
class BrowserDebrisStatus:
    available: bool
    captcha_present: bool = False
    endpoint: str | None = None
    page_url: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class BrowserDebrisSnapshot:
    status: BrowserDebrisStatus
    visible_asteroids: int = 0
    readable_square_info: int = 0
    observations: tuple[DebrisObservationFact, ...] = ()


@dataclass(frozen=True)
class DebrisReadSnapshot:
    state: DebrisReadState
    observations: tuple[DebrisObservationFact, ...]
    visible_asteroids: int = 0
    readable_square_info: int = 0
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.state not in {DebrisReadState.LIVE_UNAVAILABLE, DebrisReadState.CAPTCHA}

    @property
    def complete_current_system_evidence(self) -> bool:
        return self.state in {DebrisReadState.NO_DEBRIS, DebrisReadState.READY}


class BrowserDebrisBackend(Protocol):
    """Read-only debris boundary for the currently rendered galaxy system."""

    def read_debris(self) -> BrowserDebrisSnapshot: ...


class V2DebrisSource:
    """Classify attach-only debris evidence without inventing full-scan state."""

    def __init__(self, backend: BrowserDebrisBackend) -> None:
        self._backend = backend

    def read(self) -> DebrisReadSnapshot:
        snapshot = self._backend.read_debris()
        status = snapshot.status
        observations = tuple(snapshot.observations)
        state = classify_debris_read_state(
            browser_available=status.available,
            captcha_present=status.captcha_present,
            visible_asteroids=snapshot.visible_asteroids,
            readable_square_info=snapshot.readable_square_info,
            debris_count=len(observations),
        )
        detail = status.detail
        if state is DebrisReadState.CAPTCHA:
            detail = detail or "CAPTCHA requires manual attention"
        elif state is DebrisReadState.LIVE_UNAVAILABLE:
            detail = detail or "Debris source is unavailable"
        elif state is DebrisReadState.PARTIAL_EVIDENCE:
            detail = detail or "Current system contains unreadable asteroid evidence"
        elif state is DebrisReadState.NO_DEBRIS:
            detail = detail or "No debris in the currently opened system"
        else:
            detail = detail or f"Debris-bearing asteroids: {len(observations)}"
        return DebrisReadSnapshot(
            state=state,
            observations=observations,
            visible_asteroids=int(snapshot.visible_asteroids),
            readable_square_info=int(snapshot.readable_square_info),
            detail=detail,
        )
