from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


_COORD_RE = re.compile(r"^(\d+):(\d+):(\d+)$")


class SpyActionError(RuntimeError):
    """Base V2 spy-request contract failure."""


class SpyActionsDisabled(SpyActionError):
    """Raised when a spy mutation is requested while the shared action gate is off."""


class SpyCaptchaBlocked(SpyActionError):
    """CAPTCHA/bot verification is present; V2 must stop for manual handling."""


@dataclass(frozen=True)
class SpyRequestCommand:
    source: str
    target: str
    probe_count: int


@dataclass(frozen=True)
class SpyRequestPreparation:
    source: str
    target: str
    probe_count: int
    probe_ship_key: str
    available_probes: int
    captcha_present: bool = False
    detail: str = ""


@dataclass(frozen=True)
class SpyRequestResult:
    source: str
    target: str
    probe_count: int
    requested_at: datetime
    verified: bool
    report_id: str | None = None
    report_at: datetime | None = None
    detail: str = ""


class SpyActionBackend(Protocol):
    """Backend contract only; V2-43 intentionally has no browser implementation."""

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation: ...

    def request(
        self,
        command: SpyRequestCommand,
        preparation: SpyRequestPreparation,
    ) -> SpyRequestResult: ...

    def close(self) -> None: ...


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
    source = normalize_coord(command.source)
    target = normalize_coord(command.target)
    try:
        probe_count = int(command.probe_count)
    except (TypeError, ValueError) as exc:
        raise SpyActionError("probe_count must be an integer") from exc
    if probe_count <= 0:
        raise SpyActionError("probe_count must be greater than zero")
    if source == target:
        raise SpyActionError("target must differ from source")
    return SpyRequestCommand(source=source, target=target, probe_count=probe_count)


def validate_preparation(
    command: SpyRequestCommand,
    preparation: SpyRequestPreparation,
) -> SpyRequestPreparation:
    if preparation.captcha_present:
        raise SpyCaptchaBlocked(
            preparation.detail or "CAPTCHA detected; spy request stopped for manual handling"
        )
    if preparation.source != command.source or preparation.target != command.target:
        raise SpyActionError("Backend preparation does not match requested source/target")
    if int(preparation.probe_count) != command.probe_count:
        raise SpyActionError("Backend preparation does not match requested probe count")
    ship_key = str(preparation.probe_ship_key or "").strip()
    if not ship_key:
        raise SpyActionError("Backend did not identify the required probe ship")
    try:
        available = int(preparation.available_probes)
    except (TypeError, ValueError) as exc:
        raise SpyActionError("Backend returned invalid probe availability") from exc
    if available < 0:
        raise SpyActionError("Backend returned invalid probe availability")
    if available < command.probe_count:
        raise SpyActionError(
            f"Insufficient probes: available {available}, requested {command.probe_count}"
        )
    return SpyRequestPreparation(
        source=command.source,
        target=command.target,
        probe_count=command.probe_count,
        probe_ship_key=ship_key,
        available_probes=available,
        captcha_present=False,
        detail=str(preparation.detail or ""),
    )


class SpyActionService:
    """Single application boundary for future V2 spy-request mutations."""

    def __init__(self, backend: SpyActionBackend, *, enabled: bool = False) -> None:
        self.backend = backend
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        clean = validate_command(command)
        self._assert_enabled()
        return validate_preparation(clean, self.backend.prepare(clean))

    def request(self, command: SpyRequestCommand) -> SpyRequestResult:
        clean = validate_command(command)
        self._assert_enabled()
        preparation = validate_preparation(clean, self.backend.prepare(clean))
        result = self.backend.request(clean, preparation)
        if result.source != clean.source or result.target != clean.target:
            raise SpyActionError("Backend result does not match requested source/target")
        if int(result.probe_count) != clean.probe_count:
            raise SpyActionError("Backend result does not match requested probe count")
        if result.requested_at.tzinfo is None:
            raise SpyActionError("Backend result requested_at must be timezone-aware")
        if result.verified:
            if not str(result.report_id or "").strip() or result.report_at is None:
                raise SpyActionError("Verified spy result requires exact report identity and timestamp")
            if result.report_at.tzinfo is None:
                raise SpyActionError("Verified report_at must be timezone-aware")
        return result

    def close(self) -> None:
        self.backend.close()

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise SpyActionsDisabled("V2 spy actions are disabled")
