from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


_FLEET_ID_RE = re.compile(r"^[1-9]\d*$")
_COORD_RE = re.compile(r"^(\d+):(\d+):(\d+)$")


class SpyActionError(RuntimeError):
    """Base V2 spy-acquisition contract failure."""


class SpyActionsDisabled(SpyActionError):
    """Raised when a spy mutation is requested while the shared action gate is off."""


class SpyCaptchaBlocked(SpyActionError):
    """CAPTCHA/bot verification is present; V2 must stop for manual handling."""


class SpyRequestRejected(SpyActionError):
    """Backend proved that no remote spy side effect was accepted."""


@dataclass(frozen=True)
class SpyRequestCommand:
    """Process one already-existing Nemexia espionage fleet.

    The legacy `processSpy(fleet_id)` action is bound to an existing spy-fleet
    row. Source and target are therefore observed facts from that exact row,
    never caller-supplied routing inputs.
    """

    fleet_id: str


@dataclass(frozen=True)
class SpyRequestPreparation:
    fleet_id: str
    source: str
    target: str
    captcha_present: bool = False
    detail: str = ""


@dataclass(frozen=True)
class SpyRequestResult:
    fleet_id: str
    source: str
    target: str
    requested_at: datetime
    verified: bool
    report_id: str | None = None
    report_at: datetime | None = None
    detail: str = ""


class SpyActionBackend(Protocol):
    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation: ...

    def request(
        self,
        command: SpyRequestCommand,
        preparation: SpyRequestPreparation,
    ) -> SpyRequestResult: ...

    def close(self) -> None: ...


def normalize_fleet_id(value: object) -> str:
    text = str(value or "").strip()
    if _FLEET_ID_RE.fullmatch(text) is None:
        raise SpyActionError(f"Invalid spy fleet_id: {value!r}")
    return text


def normalize_coord(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    match = _COORD_RE.fullmatch(text)
    if match is None:
        raise SpyActionError(f"Invalid coordinate: {value!r}")
    parts = tuple(int(part) for part in match.groups())
    if any(part <= 0 for part in parts):
        raise SpyActionError(f"Invalid coordinate: {value!r}")
    return ":".join(str(part) for part in parts)


def validate_command(command: SpyRequestCommand) -> SpyRequestCommand:
    return SpyRequestCommand(fleet_id=normalize_fleet_id(command.fleet_id))


def validate_preparation(
    command: SpyRequestCommand,
    preparation: SpyRequestPreparation,
) -> SpyRequestPreparation:
    if preparation.captcha_present:
        raise SpyCaptchaBlocked(
            preparation.detail or "CAPTCHA detected; spy action stopped for manual handling"
        )
    fleet_id = normalize_fleet_id(preparation.fleet_id)
    if fleet_id != command.fleet_id:
        raise SpyActionError("Backend preparation does not match requested spy fleet_id")
    source = normalize_coord(preparation.source)
    target = normalize_coord(preparation.target)
    if source == target:
        raise SpyActionError("Spy fleet target must differ from source")
    return SpyRequestPreparation(
        fleet_id=fleet_id,
        source=source,
        target=target,
        captcha_present=False,
        detail=str(preparation.detail or ""),
    )


def validate_result(
    preparation: SpyRequestPreparation,
    result: SpyRequestResult,
) -> SpyRequestResult:
    if normalize_fleet_id(result.fleet_id) != preparation.fleet_id:
        raise SpyActionError("Backend result does not match requested spy fleet_id")
    if normalize_coord(result.source) != preparation.source or normalize_coord(result.target) != preparation.target:
        raise SpyActionError("Backend result does not match prepared source/target")
    if result.requested_at.tzinfo is None:
        raise SpyActionError("Backend result requested_at must be timezone-aware")
    if result.verified:
        if not str(result.report_id or "").strip() or result.report_at is None:
            raise SpyActionError("Verified spy result requires exact report identity and timestamp")
        if result.report_at.tzinfo is None:
            raise SpyActionError("Verified report_at must be timezone-aware")
    return result


class SpyActionService:
    """Single guarded application boundary for V2 `processSpy(fleet_id)`."""

    def __init__(self, backend: SpyActionBackend, *, enabled: bool = False) -> None:
        self.backend = backend
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        """Perform validation and read-only preparation; never process the fleet."""
        clean = validate_command(command)
        self._assert_enabled()
        return validate_preparation(clean, self.backend.prepare(clean))

    def request_prepared(
        self,
        command: SpyRequestCommand,
        preparation: SpyRequestPreparation,
    ) -> SpyRequestResult:
        """Cross the backend side-effect boundary exactly once from persisted intent."""
        clean = validate_command(command)
        self._assert_enabled()
        prepared = validate_preparation(clean, preparation)
        return validate_result(prepared, self.backend.request(clean, prepared))

    def request(self, command: SpyRequestCommand) -> SpyRequestResult:
        clean = validate_command(command)
        preparation = self.prepare(clean)
        return self.request_prepared(clean, preparation)

    def close(self) -> None:
        self.backend.close()

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise SpyActionsDisabled("V2 spy actions are disabled")
