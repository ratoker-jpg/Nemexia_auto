from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import v2.application.asteroid_actions as asteroid_actions
from v2.application.asteroid_actions import (
    AsteroidActionError,
    AsteroidActionService,
    AsteroidActionsDisabled,
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
    AsteroidPreparationRejected,
)
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds


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


def command() -> AsteroidDispatchCommand:
    return AsteroidDispatchCommand("2:22:3", observation(), recycler_count=5, safety_seconds=10)


def preparation(*, captcha: bool = False) -> AsteroidDispatchPreparation:
    obs = observation()
    prepared_at = datetime(2026, 8, 6, 17, 0, 0, tzinfo=timezone.utc)
    arrival_at = prepared_at + timedelta(seconds=300)
    return AsteroidDispatchPreparation(
        source="2:22:3",
        observation=obs,
        target="2:23:8",
        recycler_count=5,
        available_recyclers=20,
        free_fleet_slots=2,
        prepared_at=prepared_at,
        one_way_seconds=300,
        round_trip_seconds=600,
        shifts=0,
        arrival_at=arrival_at,
        return_at=prepared_at + timedelta(seconds=600),
        gas_needed=120,
        movement_margin_seconds=movement_margin_seconds(
            obs.next_move_at, obs.period_seconds, arrival_at
        ),
        captcha_present=captcha,
        detail="captcha" if captcha else "ready",
    )


def dispatch_result(*, verified: bool = True) -> AsteroidDispatchResult:
    sent_at = datetime(2026, 8, 6, 17, 0, 2, tzinfo=timezone.utc)
    return AsteroidDispatchResult(
        source="2:22:3",
        observation_coord="2:23:8",
        target="2:23:8",
        recycler_count=5,
        sent_at=sent_at,
        arrival_at=sent_at + timedelta(seconds=300),
        return_at=sent_at + timedelta(seconds=600),
        fleet_id="99123" if verified else None,
        verified=verified,
        server_info="ok",
    )


class FakeBackend:
    def __init__(
        self,
        *,
        prepared: AsteroidDispatchPreparation | None = None,
        result: AsteroidDispatchResult | None = None,
    ) -> None:
        self.prepared = prepared or preparation()
        self.result = result or dispatch_result()
        self.prepare_calls = 0
        self.dispatch_calls = 0
        self.closed = False

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        self.prepare_calls += 1
        return self.prepared

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        self.dispatch_calls += 1
        return self.result

    def close(self) -> None:
        self.closed = True


def test_action_gate_is_off_by_default_before_backend_prepare() -> None:
    backend = FakeBackend()
    service = AsteroidActionService(backend)
    with pytest.raises(AsteroidActionsDisabled):
        service.prepare(command())
    assert backend.prepare_calls == 0
    assert backend.dispatch_calls == 0


def test_command_validation_blocks_invalid_source_and_recycler_count() -> None:
    backend = FakeBackend()
    service = AsteroidActionService(backend, enabled=True)
    with pytest.raises(AsteroidActionError):
        service.prepare(replace(command(), source="bad"))
    with pytest.raises(AsteroidActionError):
        service.prepare(replace(command(), recycler_count=0))
    assert backend.prepare_calls == 0


def test_prepare_requires_exact_observation_capacity_prediction_and_margin() -> None:
    backend = FakeBackend()
    result = AsteroidActionService(backend, enabled=True).prepare(command())
    assert result.target == "2:23:8"
    assert result.shifts == 0
    assert result.available_recyclers == 20
    assert result.free_fleet_slots == 2
    assert backend.prepare_calls == 1

    with pytest.raises(AsteroidPreparationRejected, match="recyclers"):
        AsteroidActionService(
            FakeBackend(prepared=replace(preparation(), available_recyclers=4)), enabled=True
        ).prepare(command())
    with pytest.raises(AsteroidPreparationRejected, match="fleet slots"):
        AsteroidActionService(
            FakeBackend(prepared=replace(preparation(), free_fleet_slots=0)), enabled=True
        ).prepare(command())
    with pytest.raises(AsteroidPreparationRejected, match="prediction"):
        AsteroidActionService(
            FakeBackend(prepared=replace(preparation(), target="2:23:9")), enabled=True
        ).prepare(command())


def test_prepare_fails_closed_on_captcha_before_dispatch() -> None:
    backend = FakeBackend(prepared=preparation(captcha=True))
    with pytest.raises(AsteroidCaptchaBlocked):
        AsteroidActionService(backend, enabled=True).prepare(command())
    assert backend.dispatch_calls == 0


def test_margin_is_rejection_not_a_silent_target_shift() -> None:
    obs = observation()
    prepared_at = obs.next_move_at - timedelta(seconds=15)
    arrival_at = prepared_at + timedelta(seconds=10)
    near = replace(
        preparation(),
        prepared_at=prepared_at,
        one_way_seconds=10,
        round_trip_seconds=20,
        arrival_at=arrival_at,
        return_at=prepared_at + timedelta(seconds=20),
        movement_margin_seconds=5.0,
    )
    with pytest.raises(AsteroidPreparationRejected, match="too close"):
        AsteroidActionService(FakeBackend(prepared=near), enabled=True).prepare(command())


def test_dispatch_prepared_validates_exact_verified_result() -> None:
    backend = FakeBackend()
    service = AsteroidActionService(backend, enabled=True)
    prepared = service.prepare(command())
    result = service.dispatch_prepared(command(), prepared)
    assert result.verified
    assert result.fleet_id == "99123"
    assert result.target == prepared.target
    assert backend.dispatch_calls == 1


def test_unverified_remote_result_becomes_ambiguous_without_retry() -> None:
    backend = FakeBackend(result=dispatch_result(verified=False))
    service = AsteroidActionService(backend, enabled=True)
    prepared = service.prepare(command())
    with pytest.raises(AsteroidDispatchAmbiguous) as caught:
        service.dispatch_prepared(command(), prepared)
    assert caught.value.result is backend.result
    assert backend.dispatch_calls == 1


def test_boundary_has_no_browser_or_playwright_implementation() -> None:
    source = inspect.getsource(asteroid_actions)
    assert "playwright" not in source.casefold()
    assert "SendFleetButton" not in source
    assert "ajax_fleets.php" not in source
    assert "page.evaluate" not in source
