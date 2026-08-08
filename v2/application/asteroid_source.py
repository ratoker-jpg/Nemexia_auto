from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from v2.domain.asteroids import AsteroidObservationFact, AsteroidReadState, classify_read_state


@dataclass(frozen=True)
class BrowserAsteroidStatus:
    available: bool
    captcha_present: bool = False
    endpoint: str | None = None
    page_url: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class BrowserAsteroidSnapshot:
    status: BrowserAsteroidStatus
    observations: tuple[AsteroidObservationFact, ...] = ()


@dataclass(frozen=True)
class AsteroidReadSnapshot:
    state: AsteroidReadState
    observations: tuple[AsteroidObservationFact, ...]
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.state not in {AsteroidReadState.LIVE_UNAVAILABLE, AsteroidReadState.CAPTCHA}


class BrowserAsteroidBackend(Protocol):
    """Read-only boundary for the currently rendered galaxy system."""

    def read_asteroids(self) -> BrowserAsteroidSnapshot: ...


class V2AsteroidSource:
    """Classify asteroid facts obtained from an attach-only browser reader."""

    def __init__(self, backend: BrowserAsteroidBackend) -> None:
        self._backend = backend

    def read(self) -> AsteroidReadSnapshot:
        snapshot = self._backend.read_asteroids()
        status = snapshot.status
        observations = tuple(snapshot.observations)
        state = classify_read_state(
            browser_available=status.available,
            captcha_present=status.captcha_present,
            observations=observations,
        )
        if state is AsteroidReadState.CAPTCHA:
            return AsteroidReadSnapshot(state, (), status.detail or "CAPTCHA requires manual attention")
        if state is AsteroidReadState.LIVE_UNAVAILABLE:
            return AsteroidReadSnapshot(state, (), status.detail or "Asteroid source is unavailable")
        if state is AsteroidReadState.NO_ASTEROIDS:
            return AsteroidReadSnapshot(state, (), status.detail or "No asteroids in the rendered system")
        return AsteroidReadSnapshot(state, observations, status.detail or f"Asteroids: {len(observations)}")
