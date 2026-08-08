from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from v2.domain.asteroids import (
    ASTEROID_DEFAULT_SAFETY_SECONDS,
    AsteroidObservationFact,
    movement_margin_seconds,
    predict_coordinate,
)


_COORD_RE = re.compile(r"^(\d+):(\d+):(\d+)$")
_FLEET_ID_RE = re.compile(r"^[1-9]\d*$")


class AsteroidActionError(RuntimeError):
    """Base V2 asteroid-action contract failure."""


class AsteroidActionsDisabled(AsteroidActionError):
    """Shared runtime action gate is off."""


class AsteroidCaptchaBlocked(AsteroidActionError):
    """CAPTCHA/bot verification requires manual handling."""


class AsteroidPreparationRejected(AsteroidActionError):
    """Read-only preparation proves that dispatch is not currently safe."""


class AsteroidDispatchRejected(AsteroidActionError):
    """The game explicitly rejected a future SendFleet request."""


class AsteroidDispatchAmbiguous(AsteroidActionError):
    """A future SendFleet request may have reached the game; retry is forbidden."""

    def __init__(self, message: str, result: "AsteroidDispatchResult | None" = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class AsteroidDispatchCommand:
    source: str
    observation: AsteroidObservationFact
    recycler_count: int
    safety_seconds: int = ASTEROID_DEFAULT_SAFETY_SECONDS


@dataclass(frozen=True)
class AsteroidDispatchPreparation:
    source: str
    observation: AsteroidObservationFact
    target: str
    recycler_count: int
    available_recyclers: int
    free_fleet_slots: int
    prepared_at: datetime
    one_way_seconds: int
    round_trip_seconds: int
    shifts: int
    arrival_at: datetime
    return_at: datetime
    gas_needed: int | None
    movement_margin_seconds: float
    captcha_present: bool = False
    detail: str = ""


@dataclass(frozen=True)
class AsteroidDispatchResult:
    source: str
    observation_coord: str
    target: str
    recycler_count: int
    sent_at: datetime
    arrival_at: datetime
    return_at: datetime
    fleet_id: str | None
    verified: bool
    server_info: str = ""


class AsteroidActionBackend(Protocol):
    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation: ...

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult: ...

    def close(self) -> None: ...


class DisabledAsteroidActionBackend:
    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        raise AsteroidActionsDisabled("V2 asteroid actions are disabled")

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        raise AsteroidActionsDisabled("V2 asteroid actions are disabled")

    def close(self) -> None:
        return None


def normalize_coord(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    match = _COORD_RE.fullmatch(text)
    if match is None:
        raise AsteroidActionError(f"Invalid coordinate: {value!r}")
    parts = tuple(int(part) for part in match.groups())
    if any(part <= 0 for part in parts):
        raise AsteroidActionError(f"Invalid coordinate: {value!r}")
    return ":".join(str(part) for part in parts)


def validate_fleet_id(value: object) -> str:
    fleet_id = str(value or "").strip()
    if _FLEET_ID_RE.fullmatch(fleet_id) is None:
        raise AsteroidActionError("fleet_id must be a positive integer identity")
    return fleet_id


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise AsteroidActionError(f"{field} must be timezone-aware")
    return value


def validate_command(command: AsteroidDispatchCommand) -> AsteroidDispatchCommand:
    source = normalize_coord(command.source)
    observation = command.observation
    if not isinstance(observation, AsteroidObservationFact) or not observation.structurally_valid:
        raise AsteroidActionError("A structurally valid asteroid observation is required")
    try:
        recycler_count = int(command.recycler_count)
        safety_seconds = int(command.safety_seconds)
    except (TypeError, ValueError) as exc:
        raise AsteroidActionError("recycler_count and safety_seconds must be integers") from exc
    if recycler_count <= 0:
        raise AsteroidActionError("recycler_count must be greater than zero")
    if safety_seconds < 0:
        raise AsteroidActionError("safety_seconds must be non-negative")
    return AsteroidDispatchCommand(source, observation, recycler_count, safety_seconds)


def validate_preparation(
    command: AsteroidDispatchCommand,
    preparation: AsteroidDispatchPreparation,
) -> AsteroidDispatchPreparation:
    if preparation.captcha_present:
        raise AsteroidCaptchaBlocked(
            preparation.detail or "CAPTCHA detected; asteroid action stopped for manual handling"
        )
    source = normalize_coord(preparation.source)
    if source != command.source:
        raise AsteroidActionError("Backend preparation does not match requested source")
    if preparation.observation != command.observation:
        raise AsteroidActionError("Backend preparation does not match the immutable asteroid observation")
    target = normalize_coord(preparation.target)
    if target == source:
        raise AsteroidPreparationRejected("Asteroid target must differ from source")
    if int(preparation.recycler_count) != command.recycler_count:
        raise AsteroidActionError("Backend preparation does not match recycler_count")
    if int(preparation.available_recyclers) < command.recycler_count:
        raise AsteroidPreparationRejected("Not enough recyclers for asteroid dispatch")
    if int(preparation.free_fleet_slots) <= 0:
        raise AsteroidPreparationRejected("No free fleet slots for asteroid dispatch")

    prepared_at = _aware(preparation.prepared_at, "prepared_at")
    arrival_at = _aware(preparation.arrival_at, "arrival_at")
    return_at = _aware(preparation.return_at, "return_at")
    one_way = int(preparation.one_way_seconds)
    round_trip = int(preparation.round_trip_seconds)
    if one_way <= 0 or round_trip <= 0 or round_trip < one_way:
        raise AsteroidActionError("Backend returned invalid asteroid flight timing")
    if arrival_at != prepared_at + timedelta(seconds=one_way):
        raise AsteroidActionError("arrival_at does not match prepared_at + one_way_seconds")
    if return_at != prepared_at + timedelta(seconds=round_trip):
        raise AsteroidActionError("return_at does not match prepared_at + round_trip_seconds")

    predicted, shifts = predict_coordinate(command.observation, arrival_at, safety_seconds=0)
    predicted_coord = ":".join(str(value) for value in predicted)
    if target != predicted_coord or int(preparation.shifts) != shifts:
        raise AsteroidPreparationRejected("Prepared target does not match deterministic asteroid prediction")
    margin = movement_margin_seconds(
        command.observation.next_move_at,
        command.observation.period_seconds,
        arrival_at,
    )
    if margin < command.safety_seconds:
        raise AsteroidPreparationRejected(
            f"Arrival is too close to asteroid movement ({margin:.1f}s < {command.safety_seconds}s)"
        )
    if abs(float(preparation.movement_margin_seconds) - margin) > 0.001:
        raise AsteroidActionError("Backend movement margin does not match deterministic calculation")

    gas_needed = preparation.gas_needed
    if gas_needed is not None and int(gas_needed) < 0:
        raise AsteroidActionError("gas_needed must be non-negative when present")
    return AsteroidDispatchPreparation(
        source=source,
        observation=command.observation,
        target=target,
        recycler_count=command.recycler_count,
        available_recyclers=int(preparation.available_recyclers),
        free_fleet_slots=int(preparation.free_fleet_slots),
        prepared_at=prepared_at,
        one_way_seconds=one_way,
        round_trip_seconds=round_trip,
        shifts=shifts,
        arrival_at=arrival_at,
        return_at=return_at,
        gas_needed=None if gas_needed is None else int(gas_needed),
        movement_margin_seconds=margin,
        captcha_present=False,
        detail=str(preparation.detail or ""),
    )


def validate_result(
    preparation: AsteroidDispatchPreparation,
    result: AsteroidDispatchResult,
) -> AsteroidDispatchResult:
    if normalize_coord(result.source) != preparation.source:
        raise AsteroidActionError("Backend result does not match prepared source")
    if normalize_coord(result.observation_coord) != preparation.observation.coord:
        raise AsteroidActionError("Backend result does not match asteroid observation identity")
    if normalize_coord(result.target) != preparation.target:
        raise AsteroidActionError("Backend result does not match prepared target")
    if int(result.recycler_count) != preparation.recycler_count:
        raise AsteroidActionError("Backend result does not match recycler_count")
    sent_at = _aware(result.sent_at, "sent_at")
    arrival_at = _aware(result.arrival_at, "arrival_at")
    return_at = _aware(result.return_at, "return_at")
    if not (sent_at < arrival_at < return_at):
        raise AsteroidActionError("Backend result returned invalid dispatch timestamps")
    if not result.verified:
        raise AsteroidDispatchAmbiguous(
            "Asteroid dispatch may have reached the game but exact new-flight verification is missing",
            result,
        )
    fleet_id = validate_fleet_id(result.fleet_id)
    return AsteroidDispatchResult(
        source=preparation.source,
        observation_coord=preparation.observation.coord,
        target=preparation.target,
        recycler_count=preparation.recycler_count,
        sent_at=sent_at,
        arrival_at=arrival_at,
        return_at=return_at,
        fleet_id=fleet_id,
        verified=True,
        server_info=str(result.server_info or ""),
    )


class AsteroidActionService:
    """Single guarded application boundary for future V2 asteroid SendFleet."""

    def __init__(self, backend: AsteroidActionBackend, *, enabled: bool = False) -> None:
        self.backend = backend
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        clean = validate_command(command)
        self._assert_enabled()
        return validate_preparation(clean, self.backend.prepare(clean))

    def dispatch_prepared(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        clean = validate_command(command)
        self._assert_enabled()
        prepared = validate_preparation(clean, preparation)
        return validate_result(prepared, self.backend.dispatch(clean, prepared))

    def dispatch(self, command: AsteroidDispatchCommand) -> AsteroidDispatchResult:
        clean = validate_command(command)
        preparation = self.prepare(clean)
        return self.dispatch_prepared(clean, preparation)

    def close(self) -> None:
        self.backend.close()

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise AsteroidActionsDisabled("V2 asteroid actions are disabled")
