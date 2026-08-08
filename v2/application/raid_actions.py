from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


_COORD_RE = re.compile(r"^(\d+):(\d+):(\d+)$")


class RaidActionError(RuntimeError):
    """Base V2 raid-action failure."""


class RaidActionsDisabled(RaidActionError):
    """Raised when a mutating raid action is requested while V2 actions are disabled."""


class RaidDispatchAmbiguous(RaidActionError):
    """The request may have reached the game; automatic retry is forbidden."""


class RaidDispatchRejected(RaidActionError):
    """The game explicitly rejected the SendFleet request."""


@dataclass(frozen=True)
class RaidCommand:
    target: str
    player: str
    ship_count: int
    home: str


@dataclass(frozen=True)
class RaidPreparation:
    source: str
    target: str
    player: str
    ship_count: int
    one_way_seconds: int
    round_trip_seconds: int
    gas_needed: int | None = None


@dataclass(frozen=True)
class RaidDispatchResult:
    source: str
    target: str
    player: str
    ship_count: int
    sent_at: str
    arrival_at: str
    return_at: str
    fleet_id: str | None
    verified: bool
    server_info: str = ""


class RaidActionBackend(Protocol):
    def prepare(self, command: RaidCommand) -> RaidPreparation: ...
    def dispatch(self, command: RaidCommand) -> RaidDispatchResult: ...
    def close(self) -> None: ...


class DisabledRaidActionBackend:
    def prepare(self, command: RaidCommand) -> RaidPreparation:
        raise RaidActionsDisabled("V2 raid actions are disabled")

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        raise RaidActionsDisabled("V2 raid actions are disabled")

    def close(self) -> None:
        return None


def normalize_coord(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    match = _COORD_RE.fullmatch(text)
    if match is None:
        raise RaidActionError(f"Invalid coordinate: {value!r}")
    parts = tuple(int(part) for part in match.groups())
    if any(part <= 0 for part in parts):
        raise RaidActionError(f"Invalid coordinate: {value!r}")
    return ":".join(str(part) for part in parts)


def validate_command(command: RaidCommand) -> RaidCommand:
    target = normalize_coord(command.target)
    home = normalize_coord(command.home)
    try:
        ship_count = int(command.ship_count)
    except (TypeError, ValueError) as exc:
        raise RaidActionError("ship_count must be an integer") from exc
    if ship_count <= 0:
        raise RaidActionError("ship_count must be greater than zero")
    if target == home:
        raise RaidActionError("target must differ from home")
    return RaidCommand(
        target=target,
        player=str(command.player or "—").strip() or "—",
        ship_count=ship_count,
        home=home,
    )


class RaidActionService:
    """Single application boundary for every V2 raid mutation."""

    def __init__(self, backend: RaidActionBackend, *, enabled: bool = False) -> None:
        self.backend = backend
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        clean = validate_command(command)
        self._assert_enabled()
        result = self.backend.prepare(clean)
        if result.target != clean.target or result.source != clean.home:
            raise RaidActionError("Backend preparation does not match requested source/target")
        if result.ship_count != clean.ship_count:
            raise RaidActionError("Backend preparation does not match requested ship count")
        if result.one_way_seconds <= 0 or result.round_trip_seconds <= 0:
            raise RaidActionError("Backend returned invalid flight timing")
        return result

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        clean = validate_command(command)
        self._assert_enabled()
        result = self.backend.dispatch(clean)
        if result.target != clean.target or result.source != clean.home:
            raise RaidActionError("Backend dispatch does not match requested source/target")
        if result.ship_count != clean.ship_count:
            raise RaidActionError("Backend dispatch does not match requested ship count")
        if not result.sent_at or not result.arrival_at or not result.return_at:
            raise RaidActionError("Backend dispatch returned incomplete timestamps")
        return result

    def close(self) -> None:
        self.backend.close()

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise RaidActionsDisabled("V2 raid actions are disabled")
