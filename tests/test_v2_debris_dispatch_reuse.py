from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.application.debris_dispatch import DebrisDispatchReuseGate, asteroid_command_from_debris
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds
from v2.domain.debris import DebrisObservationFact
from v2.domain.debris_candidates import DebrisCandidate
from v2.persistence.database import V2Database


UTC = timezone.utc
OBSERVED = datetime(2026, 8, 6, 16, 57, 38, tzinfo=UTC)


def observation() -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 6, 16, 45, 8, tzinfo=UTC),
        next_move_at=datetime(2026, 8, 6, 17, 46, 8, tzinfo=UTC),
        period_seconds=3660,
        observed_at=OBSERVED,
    )


def candidate() -> DebrisCandidate:
    return DebrisCandidate(
        observation=DebrisObservationFact(asteroid=observation()),
        current_galaxy=2,
        current_system=23,
        current_position=8,
        shifts=0,
        persisted=True,
    )


def preparation(command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
    prepared_at = datetime(2026, 8, 6, 17, 0, 0, tzinfo=UTC)
    arrival_at = prepared_at + timedelta(seconds=300)
    return AsteroidDispatchPreparation(
        source=command.source,
        observation=command.observation,
        target="2:23:8",
        recycler_count=command.recycler_count,
        available_recyclers=50,
        free_fleet_slots=3,
        prepared_at=prepared_at,
        one_way_seconds=300,
        round_trip_seconds=600,
        shifts=0,
        arrival_at=arrival_at,
        return_at=prepared_at + timedelta(seconds=600),
        gas_needed=100,
        movement_margin_seconds=movement_margin_seconds(
            command.observation.next_move_at,
            command.observation.period_seconds,
            arrival_at,
        ),
        detail="ready",
    )


class Backend:
    def __init__(self, *, ambiguous: bool = False) -> None:
        self.ambiguous = ambiguous
        self.prepare_calls = 0
        self.dispatch_calls = 0

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        self.prepare_calls += 1
        return preparation(command)

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        prepared: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        self.dispatch_calls += 1
        if self.ambiguous:
            raise RuntimeError("connection lost after possible SendFleet")
        sent = datetime(2026, 8, 6, 17, 0, 2, tzinfo=UTC)
        return AsteroidDispatchResult(
            source=command.source,
            observation_coord=command.observation.coord,
            target=prepared.target,
            recycler_count=command.recycler_count,
            sent_at=sent,
            arrival_at=sent + timedelta(seconds=300),
            return_at=sent + timedelta(seconds=600),
            fleet_id="99123",
            verified=True,
            server_info="verified exact new recycler flight",
        )

    def close(self) -> None:
        return None


def test_debris_maps_to_exact_existing_asteroid_command() -> None:
    item = candidate()
    command = asteroid_command_from_debris(
        item,
        source="2:22:3",
        recycler_count=7,
        safety_seconds=12,
    )
    assert type(command) is AsteroidDispatchCommand
    assert command.source == "2:22:3"
    assert command.observation is item.observation.asteroid
    assert command.recycler_count == 7
    assert command.safety_seconds == 12
    assert not hasattr(command, "debris")
    assert not hasattr(command, "label")


def test_read_only_debris_preparation_is_authoritative_asteroid_preparation(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = Backend()
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        gate = DebrisDispatchReuseGate(coordinator)
        prepared = gate.prepare(candidate(), source="2:22:3", recycler_count=5)
        assert type(prepared.asteroid) is AsteroidDispatchPreparation
        assert prepared.asteroid.observation is prepared.candidate.observation.asteroid
        assert prepared.target == "2:23:8"
        assert prepared.movement_margin_seconds >= 10
        assert backend.prepare_calls == 1
        assert backend.dispatch_calls == 0


def test_debris_label_cannot_bypass_same_unresolved_asteroid_trajectory(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = Backend(ambiguous=True)
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        generic = AsteroidDispatchCommand(
            source="2:22:3",
            observation=observation(),
            recycler_count=5,
            safety_seconds=10,
        )
        with pytest.raises(RuntimeError, match="possible SendFleet"):
            coordinator.dispatch(generic, request_id="generic-asteroid-request")
        assert coordinator.record("generic-asteroid-request").status == "ambiguous"
        assert backend.dispatch_calls == 1

        # A debris-originated request uses the same coordinator/journal identity.
        # Changing request_id and recycler_count cannot create a retry namespace.
        gate = DebrisDispatchReuseGate(coordinator)
        with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
            gate.dispatch(
                candidate(),
                source="2:22:3",
                recycler_count=9,
                request_id="debris-labelled-request",
            )
        assert backend.dispatch_calls == 1
        assert gate.record("debris-labelled-request") is None


def test_verified_debris_dispatch_returns_existing_exact_flight_result(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = Backend()
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        gate = DebrisDispatchReuseGate(coordinator)
        result = gate.dispatch(
            candidate(),
            source="2:22:3",
            recycler_count=5,
            request_id="debris-verified",
        )
        assert result.verified and result.fleet_id == "99123"
        assert result.target == "2:23:8"
        record = gate.record("debris-verified")
        assert record is not None and record.status == "verified"
        assert backend.dispatch_calls == 1


def test_reuse_gate_defines_no_second_browser_or_journal_backend() -> None:
    source = inspect.getsource(DebrisDispatchReuseGate) + inspect.getsource(asteroid_command_from_debris)
    assert "AsteroidRequestCoordinator" in source
    assert "AsteroidDispatchCommand" in source
    for forbidden in (
        "debris_actions",
        "SendFleetButton",
        "playwright",
        "ajax_send_fleet",
        "sqlite3",
        "refreshGalaxy",
        ".goto(",
    ):
        assert forbidden not in source
