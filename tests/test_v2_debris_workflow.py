from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from v2.application.asteroid_actions import (
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.debris_dispatch import DebrisDispatchPreparation
from v2.application.debris_workflow import (
    DEBRIS_SELECTED_BATCH_LIMIT,
    DebrisWorkflowController,
    DebrisWorkflowState,
)
from v2.domain.asteroids import AsteroidObservationFact
from v2.domain.debris import DebrisObservationFact
from v2.domain.debris_candidates import DebrisCandidate


UTC = timezone.utc


def observation(*, system: int = 23, position: int = 8) -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=system,
        position=position,
        last_move_at=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
        next_move_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        period_seconds=3600,
        observed_at=datetime(2026, 8, 8, 8, 30, tzinfo=UTC),
    )


def candidate(*, system: int = 23, position: int = 8) -> DebrisCandidate:
    fact = DebrisObservationFact(asteroid=observation(system=system, position=position))
    return DebrisCandidate(fact, 2, system, position, 0, True)


def asteroid_prepared(item: DebrisCandidate) -> AsteroidDispatchPreparation:
    at = datetime(2026, 8, 8, 8, 40, tzinfo=UTC)
    return AsteroidDispatchPreparation(
        source="2:22:3",
        observation=item.observation.asteroid,
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


def dispatched(item: DebrisCandidate, fleet_id: str) -> AsteroidDispatchResult:
    at = datetime(2026, 8, 8, 8, 41, tzinfo=UTC)
    return AsteroidDispatchResult(
        source="2:22:3",
        observation_coord=item.observation.asteroid.coord,
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
    def __init__(
        self,
        *,
        prepare_mode: str = "ok",
        dispatch_mode: str = "ok",
    ) -> None:
        self.prepare_mode = prepare_mode
        self.dispatch_mode = dispatch_mode
        self.prepare_calls: list[DebrisCandidate] = []
        self.dispatch_calls: list[tuple[DebrisCandidate, str]] = []
        self.records: dict[str, Record] = {}
        self.on_dispatch = None

    def prepare(self, item, *, source, recycler_count, safety_seconds=10):
        self.prepare_calls.append(item)
        call = len(self.prepare_calls)
        if self.prepare_mode == "captcha" and call == 2:
            raise AsteroidCaptchaBlocked("captcha before acceptance")
        if self.prepare_mode == "error" and call == 2:
            raise RuntimeError("read-only preparation failed")
        return DebrisDispatchPreparation(item, asteroid_prepared(item))

    def dispatch(self, item, *, source, recycler_count, safety_seconds=10, request_id):
        self.dispatch_calls.append((item, request_id))
        call = len(self.dispatch_calls)
        if self.on_dispatch is not None:
            self.on_dispatch(call, item, request_id)
        if self.dispatch_mode == "captcha" and call == 2:
            raise AsteroidCaptchaBlocked("captcha")
        if self.dispatch_mode == "ambiguous" and call == 2:
            raise AsteroidDispatchAmbiguous("possible accepted side effect")
        if self.dispatch_mode == "generic_ambiguous" and call == 2:
            self.records[request_id] = Record("ambiguous")
            raise RuntimeError("connection dropped after possible acceptance")
        if self.dispatch_mode == "error" and call == 2:
            raise RuntimeError("proven safe failure")
        return dispatched(item, str(99000 + call))

    def record(self, request_id: str):
        return self.records.get(request_id)


def controller(port: Port) -> DebrisWorkflowController:
    return DebrisWorkflowController(
        port,
        confirmation_id_factory=lambda: "confirm-1",
        request_id_factory=lambda batch, index, _item: f"{batch}-req-{index}",
    )


def prepare_ready(workflow: DebrisWorkflowController, items):
    batch = workflow.prepare(
        items,
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
    )
    assert batch.state is DebrisWorkflowState.AWAITING_CONFIRMATION
    assert batch.confirmation_id == "confirm-1"
    return batch


def test_preparation_is_read_only_and_requires_explicit_confirmation() -> None:
    items = (candidate(system=23), candidate(system=22))
    port = Port()
    workflow = controller(port)
    prepared = prepare_ready(workflow, items)
    assert len(prepared.prepared) == 2
    assert len(port.prepare_calls) == 2
    assert port.dispatch_calls == []

    wrong = workflow.confirm_and_dispatch("wrong-confirmation")
    assert wrong.state is DebrisWorkflowState.STOPPED_ERROR
    assert port.dispatch_calls == []

    result = workflow.confirm_and_dispatch("confirm-1")
    assert result.state is DebrisWorkflowState.COMPLETED
    assert result.verified_count == 2
    assert len(port.dispatch_calls) == 2

    # The confirmation is single-use: a second invocation cannot replay effects.
    repeated = workflow.confirm_and_dispatch("confirm-1")
    assert repeated.state is DebrisWorkflowState.STOPPED_ERROR
    assert len(port.dispatch_calls) == 2


def test_prepare_stops_on_first_captcha_and_never_arms_confirmation() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port(prepare_mode="captcha")
    workflow = controller(port)
    result = workflow.prepare(items, source="2:22:3", recycler_count=5)
    assert result.state is DebrisWorkflowState.STOPPED_CAPTCHA
    assert len(result.prepared) == 1
    assert result.stopped_candidate == items[1]
    assert result.confirmation_id is None
    assert workflow.confirmation_id is None
    assert port.dispatch_calls == []


def test_dispatch_is_one_journaled_attempt_per_selected_candidate() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port()
    workflow = controller(port)
    prepare_ready(workflow, items)
    result = workflow.confirm_and_dispatch("confirm-1")
    assert result.state is DebrisWorkflowState.COMPLETED
    assert [step.request_id for step in result.completed] == [
        "confirm-1-req-0",
        "confirm-1-req-1",
        "confirm-1-req-2",
    ]
    assert [request_id for _item, request_id in port.dispatch_calls] == [
        "confirm-1-req-0",
        "confirm-1-req-1",
        "confirm-1-req-2",
    ]


def test_manual_stop_during_started_attempt_does_not_cancel_it_but_blocks_next() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    port = Port()
    workflow = controller(port)
    prepare_ready(workflow, items)

    def request_stop_inside_first_dispatch(call, _item, _request_id):
        if call == 1:
            workflow.request_stop()

    port.on_dispatch = request_stop_inside_first_dispatch
    result = workflow.confirm_and_dispatch("confirm-1")
    assert result.state is DebrisWorkflowState.STOPPED_MANUAL
    assert result.verified_count == 1
    assert result.completed[0].result.verified
    assert result.stopped_candidate == items[1]
    assert len(port.dispatch_calls) == 1


def test_captcha_ambiguity_and_error_stop_before_third_attempt() -> None:
    items = (candidate(system=23), candidate(system=22), candidate(system=21))
    expected = {
        "captcha": DebrisWorkflowState.STOPPED_CAPTCHA,
        "ambiguous": DebrisWorkflowState.STOPPED_AMBIGUOUS,
        "generic_ambiguous": DebrisWorkflowState.STOPPED_AMBIGUOUS,
        "error": DebrisWorkflowState.STOPPED_ERROR,
    }
    for mode, state in expected.items():
        port = Port(dispatch_mode=mode)
        workflow = controller(port)
        prepare_ready(workflow, items)
        result = workflow.confirm_and_dispatch("confirm-1")
        assert result.state is state
        assert result.verified_count == 1
        assert result.stopped_candidate == items[1]
        assert result.stopped_request_id == "confirm-1-req-1"
        assert len(port.dispatch_calls) == 2


def test_selection_is_bounded_and_duplicate_evidence_is_rejected_before_prepare() -> None:
    base = candidate()
    too_many = tuple(
        replace(base, current_position=(index % 24) + 1)
        for index in range(DEBRIS_SELECTED_BATCH_LIMIT + 1)
    )
    port = Port()
    workflow = controller(port)
    with pytest.raises(ValueError, match="exceeds"):
        workflow.prepare(too_many, source="2:22:3", recycler_count=5)
    with pytest.raises(ValueError, match="duplicate evidence"):
        workflow.prepare((base, base), source="2:22:3", recycler_count=5)
    assert port.prepare_calls == []
    assert port.dispatch_calls == []


def test_workflow_contains_no_scheduler_retry_loop_or_browser_mutation() -> None:
    source = inspect.getsource(DebrisWorkflowController)
    for forbidden in (
        "QTimer",
        ".retry(",
        "sleep(",
        "SendFleetButton",
        "playwright",
        "refreshGalaxy",
        ".goto(",
        "new_page(",
    ):
        assert forbidden not in source
