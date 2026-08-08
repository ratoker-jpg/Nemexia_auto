from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, Sequence

from v2.application.asteroid_actions import (
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchResult,
)
from v2.application.asteroid_workflow import ASTEROID_SELECTED_BATCH_LIMIT
from v2.application.debris_dispatch import DebrisDispatchPreparation
from v2.domain.debris_candidates import DebrisCandidate, debris_observation_identity


DEBRIS_SELECTED_BATCH_LIMIT = ASTEROID_SELECTED_BATCH_LIMIT


class DebrisWorkflowState(str, Enum):
    EMPTY = "empty"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    STOPPED_MANUAL = "stopped_manual"
    STOPPED_CAPTCHA = "stopped_captcha"
    STOPPED_AMBIGUOUS = "stopped_ambiguous"
    STOPPED_ERROR = "stopped_error"


@dataclass(frozen=True)
class DebrisPreparedCandidate:
    candidate: DebrisCandidate
    preparation: DebrisDispatchPreparation


@dataclass(frozen=True)
class DebrisPreparationBatch:
    state: DebrisWorkflowState
    prepared: tuple[DebrisPreparedCandidate, ...]
    confirmation_id: str | None = None
    stopped_candidate: DebrisCandidate | None = None
    detail: str = ""


@dataclass(frozen=True)
class DebrisDispatchStep:
    candidate: DebrisCandidate
    request_id: str
    result: AsteroidDispatchResult


@dataclass(frozen=True)
class DebrisDispatchBatch:
    state: DebrisWorkflowState
    completed: tuple[DebrisDispatchStep, ...]
    stopped_candidate: DebrisCandidate | None = None
    stopped_request_id: str | None = None
    detail: str = ""

    @property
    def verified_count(self) -> int:
        return len(self.completed)


class DebrisWorkflowPort(Protocol):
    def prepare(
        self,
        candidate: DebrisCandidate,
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> DebrisDispatchPreparation: ...

    def dispatch(
        self,
        candidate: DebrisCandidate,
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
        request_id: str,
    ) -> AsteroidDispatchResult: ...

    def record(self, request_id: str): ...


def _bounded_unique(candidates: Sequence[DebrisCandidate]) -> tuple[DebrisCandidate, ...]:
    selected = tuple(candidates)
    if len(selected) > DEBRIS_SELECTED_BATCH_LIMIT:
        raise ValueError(
            f"Selected debris batch exceeds {DEBRIS_SELECTED_BATCH_LIMIT} candidates"
        )
    seen: set[tuple[object, ...]] = set()
    for candidate in selected:
        identity = debris_observation_identity(candidate.observation)
        if identity in seen:
            raise ValueError("Selected debris batch contains duplicate evidence")
        seen.add(identity)
    return selected


class DebrisWorkflowController:
    """Explicit prepare -> confirm -> bounded dispatch workflow.

    Preparation is read-only. The opaque confirmation identity is created only
    after every selected candidate prepared successfully. Dispatch then delegates
    each candidate to the shared asteroid request coordinator, which performs its
    own fresh live preparation immediately before the one journaled side effect.

    Manual stop is checked only between candidates. An already-started remote
    attempt is never cancelled and is allowed to finish into verified/ambiguous
    journal state. This controller contains no scheduler and performs no retry.
    """

    def __init__(
        self,
        port: DebrisWorkflowPort,
        *,
        request_id_factory: Callable[[str, int, DebrisCandidate], str] | None = None,
        confirmation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.port = port
        self._request_id_factory = request_id_factory or (
            lambda batch_id, index, _candidate: f"debris-{batch_id}-{index}-{uuid.uuid4().hex}"
        )
        self._confirmation_id_factory = confirmation_id_factory or (
            lambda: f"debris-confirm-{uuid.uuid4().hex}"
        )
        self._prepared: tuple[DebrisPreparedCandidate, ...] = ()
        self._confirmation_id: str | None = None
        self._source = ""
        self._recycler_count = 0
        self._safety_seconds = 10
        self._stop_requested = False

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def confirmation_id(self) -> str | None:
        return self._confirmation_id

    def request_stop(self) -> None:
        self._stop_requested = True

    def clear_stop(self) -> None:
        self._stop_requested = False

    def cancel_prepared(self) -> None:
        """Disarm a not-yet-confirmed batch without touching the journal/browser."""
        self._prepared = ()
        self._confirmation_id = None

    def prepare(
        self,
        candidates: Sequence[DebrisCandidate],
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> DebrisPreparationBatch:
        selected = _bounded_unique(candidates)
        self.cancel_prepared()
        self._source = str(source)
        self._recycler_count = int(recycler_count)
        self._safety_seconds = int(safety_seconds)
        self._stop_requested = False
        if not selected:
            return DebrisPreparationBatch(
                DebrisWorkflowState.EMPTY,
                (),
                detail="No debris candidates selected",
            )

        prepared: list[DebrisPreparedCandidate] = []
        for candidate in selected:
            try:
                facts = self.port.prepare(
                    candidate,
                    source=self._source,
                    recycler_count=self._recycler_count,
                    safety_seconds=self._safety_seconds,
                )
            except AsteroidCaptchaBlocked as exc:
                return DebrisPreparationBatch(
                    DebrisWorkflowState.STOPPED_CAPTCHA,
                    tuple(prepared),
                    stopped_candidate=candidate,
                    detail=str(exc),
                )
            except Exception as exc:
                return DebrisPreparationBatch(
                    DebrisWorkflowState.STOPPED_ERROR,
                    tuple(prepared),
                    stopped_candidate=candidate,
                    detail=str(exc),
                )
            prepared.append(DebrisPreparedCandidate(candidate, facts))

        confirmation_id = str(self._confirmation_id_factory() or "").strip()
        if not confirmation_id:
            return DebrisPreparationBatch(
                DebrisWorkflowState.STOPPED_ERROR,
                tuple(prepared),
                detail="confirmation identity factory returned an empty identity",
            )
        self._prepared = tuple(prepared)
        self._confirmation_id = confirmation_id
        return DebrisPreparationBatch(
            DebrisWorkflowState.AWAITING_CONFIRMATION,
            self._prepared,
            confirmation_id=confirmation_id,
            detail=f"Prepared {len(prepared)} debris dispatches; explicit confirmation required",
        )

    def confirm_and_dispatch(
        self,
        confirmation_id: str,
        *,
        between_attempts: Callable[[], None] | None = None,
    ) -> DebrisDispatchBatch:
        supplied = str(confirmation_id or "").strip()
        expected = self._confirmation_id
        prepared = self._prepared
        if not expected or not prepared:
            return DebrisDispatchBatch(
                DebrisWorkflowState.STOPPED_ERROR,
                (),
                detail="No prepared debris batch is awaiting confirmation",
            )
        if supplied != expected:
            return DebrisDispatchBatch(
                DebrisWorkflowState.STOPPED_ERROR,
                (),
                detail="Explicit debris confirmation identity does not match prepared batch",
            )

        # Consume the confirmation before any side effect. A caller cannot invoke
        # confirm twice against the same prepared batch even if the first attempt
        # later stops or becomes ambiguous.
        self.cancel_prepared()
        completed: list[DebrisDispatchStep] = []
        for index, item in enumerate(prepared):
            candidate = item.candidate
            if between_attempts is not None:
                between_attempts()
            if self._stop_requested:
                return DebrisDispatchBatch(
                    DebrisWorkflowState.STOPPED_MANUAL,
                    tuple(completed),
                    stopped_candidate=candidate,
                    detail="Manual stop requested before next debris side effect",
                )
            request_id = str(
                self._request_id_factory(expected, index, candidate) or ""
            ).strip()
            if not request_id:
                return DebrisDispatchBatch(
                    DebrisWorkflowState.STOPPED_ERROR,
                    tuple(completed),
                    stopped_candidate=candidate,
                    detail="request_id factory returned an empty identity",
                )
            try:
                result = self.port.dispatch(
                    candidate,
                    source=self._source,
                    recycler_count=self._recycler_count,
                    safety_seconds=self._safety_seconds,
                    request_id=request_id,
                )
            except AsteroidCaptchaBlocked as exc:
                return DebrisDispatchBatch(
                    DebrisWorkflowState.STOPPED_CAPTCHA,
                    tuple(completed),
                    stopped_candidate=candidate,
                    stopped_request_id=request_id,
                    detail=str(exc),
                )
            except AsteroidDispatchAmbiguous as exc:
                return DebrisDispatchBatch(
                    DebrisWorkflowState.STOPPED_AMBIGUOUS,
                    tuple(completed),
                    stopped_candidate=candidate,
                    stopped_request_id=request_id,
                    detail=str(exc),
                )
            except Exception as exc:
                record = self.port.record(request_id)
                state = (
                    DebrisWorkflowState.STOPPED_AMBIGUOUS
                    if record is not None and getattr(record, "status", None) == "ambiguous"
                    else DebrisWorkflowState.STOPPED_ERROR
                )
                return DebrisDispatchBatch(
                    state,
                    tuple(completed),
                    stopped_candidate=candidate,
                    stopped_request_id=request_id,
                    detail=str(exc),
                )
            completed.append(DebrisDispatchStep(candidate, request_id, result))

        return DebrisDispatchBatch(
            DebrisWorkflowState.COMPLETED,
            tuple(completed),
            detail=f"Verified {len(completed)} debris dispatches",
        )
