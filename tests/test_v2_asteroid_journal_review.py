from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.application.asteroid_actions import (
    AsteroidActionError,
    AsteroidActionService,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds, predict_coordinate
from v2.persistence.database import V2Database


def observation(*, offset_hours: int = 0) -> AsteroidObservationFact:
    offset = timezone(timedelta(hours=offset_hours))
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 6, 16 + offset_hours, 45, 8, tzinfo=offset),
        next_move_at=datetime(2026, 8, 6, 17 + offset_hours, 46, 8, tzinfo=offset),
        period_seconds=3660,
        observed_at=datetime(2026, 8, 6, 16 + offset_hours, 57, 38, tzinfo=offset),
    )


class DynamicBackend:
    def __init__(self, *, unverified: bool = True) -> None:
        self.unverified = unverified
        self.dispatch_calls = 0

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        prepared_at = datetime(2026, 8, 6, 17, 0, 0, tzinfo=timezone.utc)
        arrival_at = prepared_at + timedelta(seconds=300)
        target_tuple, shifts = predict_coordinate(command.observation, arrival_at, safety_seconds=0)
        target = ":".join(str(value) for value in target_tuple)
        return AsteroidDispatchPreparation(
            source=command.source,
            observation=command.observation,
            target=target,
            recycler_count=command.recycler_count,
            available_recyclers=20,
            free_fleet_slots=2,
            prepared_at=prepared_at,
            one_way_seconds=300,
            round_trip_seconds=600,
            shifts=shifts,
            arrival_at=arrival_at,
            return_at=prepared_at + timedelta(seconds=600),
            gas_needed=120,
            movement_margin_seconds=movement_margin_seconds(
                command.observation.next_move_at,
                command.observation.period_seconds,
                arrival_at,
            ),
        )

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        self.dispatch_calls += 1
        sent_at = datetime(2026, 8, 6, 17, 0, 2, tzinfo=timezone.utc)
        return AsteroidDispatchResult(
            source=preparation.source,
            observation_coord=preparation.observation.coord,
            target=preparation.target,
            recycler_count=preparation.recycler_count,
            sent_at=sent_at,
            arrival_at=sent_at + timedelta(seconds=preparation.one_way_seconds),
            return_at=sent_at + timedelta(seconds=preparation.round_trip_seconds),
            fleet_id="99123",
            verified=not self.unverified,
            server_info="server evidence retained",
        )

    def close(self) -> None:
        return None


def test_timezone_equivalent_trajectory_cannot_bypass_unresolved_identity(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        first_backend = DynamicBackend(unverified=True)
        first = AsteroidRequestCoordinator(AsteroidActionService(first_backend, enabled=True), db)
        with pytest.raises(AsteroidDispatchAmbiguous):
            first.dispatch(
                AsteroidDispatchCommand("2:22:3", observation(offset_hours=0), 5, 10),
                request_id="offset-a",
            )
        first_record = first.record("offset-a")
        assert first_record is not None
        assert first_record.observation_next_move_at == "2026-08-06T17:46:08+00:00"

    with V2Database(path) as db:
        second_backend = DynamicBackend(unverified=True)
        second = AsteroidRequestCoordinator(AsteroidActionService(second_backend, enabled=True), db)
        # Same instants represented as +02:00 must hit the same canonical journal key.
        with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
            second.dispatch(
                AsteroidDispatchCommand("2:22:3", observation(offset_hours=2), 7, 10),
                request_id="offset-b",
            )
        assert second_backend.dispatch_calls == 0


def test_structured_ambiguous_result_keeps_recovery_evidence(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = DynamicBackend(unverified=True)
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        with pytest.raises(AsteroidDispatchAmbiguous):
            coordinator.dispatch(
                AsteroidDispatchCommand("2:22:3", observation(), 5, 10),
                request_id="evidence",
            )
        record = coordinator.record("evidence")
        assert record is not None and record.status == "ambiguous"
        assert record.fleet_id == "99123"
        assert record.sent_at == "2026-08-06T17:00:02+00:00"
        assert record.arrival_at == "2026-08-06T17:05:02+00:00"
        assert record.return_at == "2026-08-06T17:10:02+00:00"
        assert "server evidence retained" in record.detail


def test_manual_reconciliation_requires_same_positive_numeric_fleet_identity_contract(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = AsteroidRequestCoordinator(
            AsteroidActionService(DynamicBackend(unverified=True), enabled=True), db
        )
        with pytest.raises(AsteroidDispatchAmbiguous):
            coordinator.dispatch(
                AsteroidDispatchCommand("2:22:3", observation(), 5, 10),
                request_id="bad-fleet",
            )
        with pytest.raises(AsteroidActionError, match="positive integer"):
            coordinator.resolve_verified("bad-fleet", fleet_id="abc")
        record = coordinator.record("bad-fleet")
        assert record is not None and record.status == "ambiguous"
