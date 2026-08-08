from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from v2.application.asteroid_actions import (
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_workflow import (
    ASTEROID_SELECTED_BATCH_LIMIT,
    AsteroidWorkflowState,
    dispatch_selected_asteroids,
    prepare_selected_asteroids,
)
from v2.domain.asteroid_candidates import AsteroidCandidate
from v2.domain.asteroids import AsteroidObservationFact


def observation(*, system: int = 23, position: int = 8) -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=system,
        position=position,
        last_move_at=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        period_seconds=3600,
        observed_at=datetime(2026, 8, 8, 8, 30, tzinfo=timezone.utc),
    )


def candidate(*, system: int = 23, position: int = 8) -> AsteroidCandidate:
    fact = observation(system=system, position=position)
    return AsteroidCandidate(fact, 2, system, position, 0, True)


def prepared(item: AsteroidCandidate) -> AsteroidDispatchPreparation:
    at = datetime(2026, 8, 8, 8, 40, tzinfo=timezone.utc)
    return AsteroidDispatchPreparation(
        source="2:22:3",
        observation=item.observation,
        target=item.current_coord,
        recycler_count=5,
        available_recyclers=50,
        free_fleet_slots=10,
        prepared_at=at,
        one_way_seconds=300,
        round_trip_seconds=600,
        shifts=0,
        arrival_at=at + timedelta(seconds=300),
        return_at=at + timedelta(seconds=600),
        gas_needed=100,
        movement_margin_seconds=1200.0,
    )


def dispatched(item: AsteroidCandidate, fleet_id: str) -> AsteroidDispatchResult:
    at = datetime(2026, 8, 8, 8, 41, tzinfo=timezone.utc)
    return AsteroidDispatchResult(
        source="2:22:3",
        observation_coord=item.observation.coord,
        target=item.current_coord,
        recycler_count=5,
        sent_at=at,
        arrival_at=at + timedelta(seconds=300),
        return_at=at + timedelta(seconds=600),
        fleet_id=fleet_id,
        verified=True,
    )


class Record:
    def __init__(self, status: str) -> None:
        self.status = status


class Port:
    def __init__(self, *, prepare_fail_at: int | None = None, dispatch_mode: str = "ok") -> None:
        self.prepare_fail_at = prepare_fail_at
        self.dispatch_mode = dispatch_mode
        self.prepare_calls: list[AsteroidCandidate] = []
        self.dispatch_calls: list[AsteroidCandidate] = []
        self.records: dict[str, Record] = {}

    def prepare_asteroid(self, *, source, observation, recycler_count, safety_seconds=10):
        item = AsteroidCandidate(observation, observation.galaxy, observation.system, observation.position, 0, True)
        self.prepare_calls.append(item)
        if self.prepare_fail_at is not None and len(self.prepare_calls) == self.prepare_fail_at:
            raise AsteroidCaptchaBlocked("captcha")
        return prepared(item)

    def dispatch_asteroid(self, *, source, observation, recycler_count, safety_seconds=10, request_id):
        item = AsteroidCandidate(observation, observation.galaxy, observation.system, observation.position, 0, True)
        self.dispatch_calls.append(item)
        call = len(self.dispatch_calls)
        if self.dispatch_mode == "ambiguous" and call == 2:
            raise AsteroidDispatchAmbiguous("unverified")
        if self.dispatch_mode == "generic_ambiguous" and call == 2:
            self.records[request_id] = Record("ambiguous")
            raise RuntimeError("connection dropped")
        if self.dispatch_mode == "error" and call == 2:
            raise RuntimeError("safe preparation failure")
        return dispatched(item, str(99000 + call))

    def asteroid_action_record(self, request_id: str):
        return self.records.get(request_id)


def test_read_only_preparation_stops_at_first_captcha() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port(prepare_fail_at=2)
    result = prepare_selected_asteroids(
        port, items, source="2:22:3", recycler_count=5, safety_seconds=10
    )
    assert result.state is AsteroidWorkflowState.STOPPED_CAPTCHA
    assert len(result.prepared) == 1
    assert result.stopped_candidate == items[1]
    assert len(port.prepare_calls) == 2


def test_dispatch_series_is_exactly_once_per_selected_candidate() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port()
    result = dispatch_selected_asteroids(
        port,
        items,
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
        request_id_factory=lambda index, _item: f"req-{index}",
    )
    assert result.state is AsteroidWorkflowState.COMPLETED
    assert result.verified_count == 3
    assert [step.request_id for step in result.completed] == ["req-0", "req-1", "req-2"]
    assert len(port.dispatch_calls) == 3


def test_ambiguous_dispatch_stops_series_without_retry_or_third_attempt() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port(dispatch_mode="ambiguous")
    result = dispatch_selected_asteroids(
        port,
        items,
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
        request_id_factory=lambda index, _item: f"req-{index}",
    )
    assert result.state is AsteroidWorkflowState.STOPPED_AMBIGUOUS
    assert result.verified_count == 1
    assert result.stopped_request_id == "req-1"
    assert len(port.dispatch_calls) == 2


def test_unclassified_failure_uses_journal_status_to_preserve_ambiguity() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port(dispatch_mode="generic_ambiguous")
    result = dispatch_selected_asteroids(
        port,
        items,
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
        request_id_factory=lambda index, _item: f"req-{index}",
    )
    assert result.state is AsteroidWorkflowState.STOPPED_AMBIGUOUS
    assert result.verified_count == 1
    assert len(port.dispatch_calls) == 2


def test_non_ambiguous_error_stops_series_without_continuing() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port(dispatch_mode="error")
    result = dispatch_selected_asteroids(
        port,
        items,
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
        request_id_factory=lambda index, _item: f"req-{index}",
    )
    assert result.state is AsteroidWorkflowState.STOPPED_ERROR
    assert result.verified_count == 1
    assert len(port.dispatch_calls) == 2


def test_selection_is_bounded_before_any_prepare_or_dispatch() -> None:
    base = candidate()
    items = tuple(
        replace(base, current_position=(index % 24) + 1)
        for index in range(ASTEROID_SELECTED_BATCH_LIMIT + 1)
    )
    port = Port()
    with pytest.raises(ValueError, match="exceeds"):
        prepare_selected_asteroids(
            port, items, source="2:22:3", recycler_count=5, safety_seconds=10
        )
    with pytest.raises(ValueError, match="exceeds"):
        dispatch_selected_asteroids(
            port, items, source="2:22:3", recycler_count=5, safety_seconds=10
        )
    assert port.prepare_calls == []
    assert port.dispatch_calls == []
