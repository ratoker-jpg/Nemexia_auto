from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, Sequence

from v2.application.asteroid_actions import (
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.domain.asteroid_candidates import AsteroidCandidate


ASTEROID_SELECTED_BATCH_LIMIT = 200


class AsteroidWorkflowState(str, Enum):
    EMPTY = "empty"
    READY = "ready"
    COMPLETED = "completed"
    STOPPED_CAPTCHA = "stopped_captcha"
    STOPPED_AMBIGUOUS = "stopped_ambiguous"
    STOPPED_ERROR = "stopped_error"


@dataclass(frozen=True)
class AsteroidPreparedCandidate:
    candidate: AsteroidCandidate
    preparation: AsteroidDispatchPreparation


@dataclass(frozen=True)
class AsteroidPreparationBatch:
    state: AsteroidWorkflowState
    prepared: tuple[AsteroidPreparedCandidate, ...]
    stopped_candidate: AsteroidCandidate | None = None
    detail: str = ""


@dataclass(frozen=True)
class AsteroidDispatchStep:
    candidate: AsteroidCandidate
    request_id: str
    result: AsteroidDispatchResult


@dataclass(frozen=True)
class AsteroidDispatchBatch:
    state: AsteroidWorkflowState
    completed: tuple[AsteroidDispatchStep, ...]
    stopped_candidate: AsteroidCandidate | None = None
    stopped_request_id: str | None = None
    detail: str = ""

    @property
    def verified_count(self) -> int:
        return len(self.completed)


class AsteroidWorkflowPort(Protocol):
    def prepare_asteroid(
        self,
        *,
        source: str,
        observation,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> AsteroidDispatchPreparation: ...

    def dispatch_asteroid(
        self,
        *,
        source: str,
        observation,
        recycler_count: int,
        safety_seconds: int = 10,
        request_id: str,
    ) -> AsteroidDispatchResult: ...

    def asteroid_action_record(self, request_id: str): ...


def _bounded(candidates: Sequence[AsteroidCandidate]) -> tuple[AsteroidCandidate, ...]:
    selected = tuple(candidates)
    if len(selected) > ASTEROID_SELECTED_BATCH_LIMIT:
        raise ValueError(
            f"Selected asteroid batch exceeds {ASTEROID_SELECTED_BATCH_LIMIT} candidates"
        )
    return selected


def prepare_selected_asteroids(
    port: AsteroidWorkflowPort,
    candidates: Sequence[AsteroidCandidate],
    *,
    source: str,
    recycler_count: int,
    safety_seconds: int,
) -> AsteroidPreparationBatch:
    """Read-only readiness pass over an explicit bounded selection."""

    selected = _bounded(candidates)
    if not selected:
        return AsteroidPreparationBatch(AsteroidWorkflowState.EMPTY, (), detail="No asteroids selected")

    prepared: list[AsteroidPreparedCandidate] = []
    for candidate in selected:
        try:
            facts = port.prepare_asteroid(
                source=source,
                observation=candidate.observation,
                recycler_count=recycler_count,
                safety_seconds=safety_seconds,
            )
        except AsteroidCaptchaBlocked as exc:
            return AsteroidPreparationBatch(
                AsteroidWorkflowState.STOPPED_CAPTCHA,
                tuple(prepared),
                candidate,
                str(exc),
            )
        except Exception as exc:
            return AsteroidPreparationBatch(
                AsteroidWorkflowState.STOPPED_ERROR,
                tuple(prepared),
                candidate,
                str(exc),
            )
        prepared.append(AsteroidPreparedCandidate(candidate, facts))
    return AsteroidPreparationBatch(
        AsteroidWorkflowState.READY,
        tuple(prepared),
        detail=f"Prepared {len(prepared)} asteroid dispatches",
    )


def dispatch_selected_asteroids(
    port: AsteroidWorkflowPort,
    candidates: Sequence[AsteroidCandidate],
    *,
    source: str,
    recycler_count: int,
    safety_seconds: int,
    request_id_factory: Callable[[int, AsteroidCandidate], str] | None = None,
) -> AsteroidDispatchBatch:
    """Dispatch an explicit bounded selection with no retry and first-error stop."""

    selected = _bounded(candidates)
    if not selected:
        return AsteroidDispatchBatch(AsteroidWorkflowState.EMPTY, (), detail="No asteroids selected")
    factory = request_id_factory or (
        lambda _index, _candidate: f"asteroid-{uuid.uuid4().hex}"
    )

    completed: list[AsteroidDispatchStep] = []
    for index, candidate in enumerate(selected):
        request_id = str(factory(index, candidate) or "").strip()
        if not request_id:
            return AsteroidDispatchBatch(
                AsteroidWorkflowState.STOPPED_ERROR,
                tuple(completed),
                candidate,
                None,
                "request_id factory returned an empty identity",
            )
        try:
            result = port.dispatch_asteroid(
                source=source,
                observation=candidate.observation,
                recycler_count=recycler_count,
                safety_seconds=safety_seconds,
                request_id=request_id,
            )
        except AsteroidCaptchaBlocked as exc:
            return AsteroidDispatchBatch(
                AsteroidWorkflowState.STOPPED_CAPTCHA,
                tuple(completed),
                candidate,
                request_id,
                str(exc),
            )
        except AsteroidDispatchAmbiguous as exc:
            return AsteroidDispatchBatch(
                AsteroidWorkflowState.STOPPED_AMBIGUOUS,
                tuple(completed),
                candidate,
                request_id,
                str(exc),
            )
        except Exception as exc:
            record = port.asteroid_action_record(request_id)
            state = (
                AsteroidWorkflowState.STOPPED_AMBIGUOUS
                if record is not None and getattr(record, "status", None) == "ambiguous"
                else AsteroidWorkflowState.STOPPED_ERROR
            )
            return AsteroidDispatchBatch(
                state,
                tuple(completed),
                candidate,
                request_id,
                str(exc),
            )
        completed.append(AsteroidDispatchStep(candidate, request_id, result))

    return AsteroidDispatchBatch(
        AsteroidWorkflowState.COMPLETED,
        tuple(completed),
        detail=f"Verified {len(completed)} asteroid dispatches",
    )
