from __future__ import annotations

from datetime import datetime, timezone

from v2.application.asteroid_source import (
    BrowserAsteroidSnapshot,
    BrowserAsteroidStatus,
    V2AsteroidSource,
)
from v2.domain.asteroids import AsteroidObservationFact, AsteroidReadState


class FakeBackend:
    def __init__(self, snapshot: BrowserAsteroidSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def read_asteroids(self) -> BrowserAsteroidSnapshot:
        self.calls += 1
        return self.snapshot


def observation() -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 6, 16, 45, 8, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 6, 17, 46, 8, tzinfo=timezone.utc),
        period_seconds=3660,
        observed_at=datetime(2026, 8, 6, 16, 57, 38, tzinfo=timezone.utc),
    )


def test_unavailable_is_not_treated_as_empty_system() -> None:
    backend = FakeBackend(BrowserAsteroidSnapshot(BrowserAsteroidStatus(False, detail="open galaxy")))
    result = V2AsteroidSource(backend).read()
    assert result.state is AsteroidReadState.LIVE_UNAVAILABLE
    assert not result.available
    assert result.observations == ()
    assert backend.calls == 1


def test_captcha_has_priority_and_drops_observations() -> None:
    backend = FakeBackend(
        BrowserAsteroidSnapshot(
            BrowserAsteroidStatus(False, captcha_present=True, detail="captcha"),
            (observation(),),
        )
    )
    result = V2AsteroidSource(backend).read()
    assert result.state is AsteroidReadState.CAPTCHA
    assert result.observations == ()


def test_available_empty_system_is_typed_no_asteroids() -> None:
    result = V2AsteroidSource(
        FakeBackend(BrowserAsteroidSnapshot(BrowserAsteroidStatus(True)))
    ).read()
    assert result.state is AsteroidReadState.NO_ASTEROIDS
    assert result.available


def test_proven_observations_are_ready_without_ui_text_logic() -> None:
    item = observation()
    result = V2AsteroidSource(
        FakeBackend(BrowserAsteroidSnapshot(BrowserAsteroidStatus(True), (item,)))
    ).read()
    assert result.state is AsteroidReadState.READY
    assert result.observations == (item,)
