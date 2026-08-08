from __future__ import annotations

from dataclasses import dataclass

from v2.application.raid_actions import (
    RaidActionError,
    RaidActionService,
    RaidActionsDisabled,
    RaidCommand,
    RaidDispatchResult,
    validate_command,
)
from v2.persistence.database import V2Database, V2DatabaseError


class RaidRequestBlocked(RaidActionError):
    """A request is duplicate or conflicts with an unresolved earlier send."""


@dataclass(frozen=True)
class RaidActionRecord:
    request_id: str
    source: str
    target: str
    player: str
    ship_count: int
    status: str
    fleet_id: str | None
    detail: str


class RaidDispatchCoordinator:
    """Journal intent before SendFleet and refuse unsafe duplicate attempts."""

    def __init__(self, service: RaidActionService, database: V2Database) -> None:
        self.service = service
        self.database = database

    def dispatch(self, command: RaidCommand, *, request_id: str) -> RaidDispatchResult:
        clean = validate_command(command)
        request_id = str(request_id or "").strip()
        if not request_id:
            raise RaidRequestBlocked("request_id is required")
        if not self.service.enabled:
            raise RaidActionsDisabled("V2 raid actions are disabled")

        existing = self.database.read_raid_action(request_id)
        if existing is not None:
            raise RaidRequestBlocked(
                f"Raid request {request_id} already exists with status {existing['status']}"
            )
        unresolved = self.database.unresolved_raid_action(source=clean.home, target=clean.target)
        if unresolved is not None:
            raise RaidRequestBlocked(
                "Есть незавершённая или неоднозначная отправка на эту цель: "
                f"{unresolved['request_id']} · {unresolved['status']}"
            )

        try:
            self.database.begin_raid_action(
                request_id=request_id,
                source=clean.home,
                target=clean.target,
                player=clean.player,
                ship_count=clean.ship_count,
            )
        except V2DatabaseError as exc:
            raise RaidRequestBlocked(str(exc)) from exc

        try:
            result = self.service.dispatch(clean)
        except Exception as exc:
            # The backend may have crossed the SendFleet boundary before an exception
            # (network timeout, unreadable response, CAPTCHA during verification, etc.).
            # Conservatively mark it ambiguous. A later reconciliation step must clear it;
            # never auto-retry after an unknown side effect.
            self.database.finish_raid_action(
                request_id,
                status="ambiguous",
                detail=str(exc),
            )
            raise

        status = "verified" if result.verified else "ambiguous"
        self.database.finish_raid_action(
            request_id,
            status=status,
            fleet_id=result.fleet_id,
            sent_at=result.sent_at,
            arrival_at=result.arrival_at,
            return_at=result.return_at,
            detail=result.server_info,
        )
        return result

    def record(self, request_id: str) -> RaidActionRecord | None:
        row = self.database.read_raid_action(request_id)
        if row is None:
            return None
        return RaidActionRecord(
            request_id=str(row["request_id"]),
            source=str(row["source"]),
            target=str(row["target"]),
            player=str(row["player"]),
            ship_count=int(row["ship_count"]),
            status=str(row["status"]),
            fleet_id=str(row["fleet_id"]) if row.get("fleet_id") is not None else None,
            detail=str(row.get("detail") or ""),
        )

    def recent(self, *, limit: int = 200) -> list[RaidActionRecord]:
        records: list[RaidActionRecord] = []
        for row in self.database.list_raid_actions(limit=limit):
            records.append(
                RaidActionRecord(
                    request_id=str(row["request_id"]),
                    source=str(row["source"]),
                    target=str(row["target"]),
                    player=str(row["player"]),
                    ship_count=int(row["ship_count"]),
                    status=str(row["status"]),
                    fleet_id=str(row["fleet_id"]) if row.get("fleet_id") is not None else None,
                    detail=str(row.get("detail") or ""),
                )
            )
        return records
