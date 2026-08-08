from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from v2.application.spy_actions import (
    SpyActionError,
    SpyActionService,
    SpyActionsDisabled,
    SpyRequestCommand,
    SpyRequestPreparation,
    SpyRequestRejected,
    SpyRequestResult,
    validate_command,
)
from v2.persistence.database import V2Database, V2DatabaseError


class SpyRequestBlocked(SpyActionError):
    """A request ID or spy fleet has unresolved immutable intent."""


@dataclass(frozen=True)
class SpyActionRecord:
    request_id: str
    fleet_id: str | None
    source: str
    target: str
    status: str
    report_id: str | None
    requested_at: str | None
    report_at: str | None
    created_at: str
    detail: str


class SpyRequestCoordinator:
    """Persist exact spy-fleet intent before one `processSpy(fleet_id)` attempt."""

    def __init__(self, service: SpyActionService, database: V2Database) -> None:
        self.service = service
        self.database = database

    def request(self, command: SpyRequestCommand, *, request_id: str) -> SpyRequestResult:
        clean = validate_command(command)
        request_id = str(request_id or "").strip()
        if not request_id:
            raise SpyRequestBlocked("request_id is required")
        if not self.service.enabled:
            raise SpyActionsDisabled("V2 spy actions are disabled")

        existing = self.database.read_spy_action(request_id)
        if existing is not None:
            raise SpyRequestBlocked(
                f"Spy request {request_id} already exists with status {existing['status']}"
            )
        unresolved_fleet = self.database.unresolved_spy_action(fleet_id=clean.fleet_id)
        if unresolved_fleet is not None:
            raise SpyRequestBlocked(
                "Есть незавершённая или неоднозначная обработка spy fleet: "
                f"{unresolved_fleet['request_id']} · {unresolved_fleet['status']}"
            )

        # Preparation is read-only and derives source/target from the exact row.
        preparation = self.service.prepare(clean)
        unresolved_target = self.database.unresolved_spy_target(
            source=preparation.source,
            target=preparation.target,
        )
        if unresolved_target is not None:
            raise SpyRequestBlocked(
                "Есть незавершённая или неоднозначная разведка на эту цель: "
                f"{unresolved_target['request_id']} · {unresolved_target['status']}"
            )
        self._begin(request_id, preparation)

        try:
            result = self.service.request_prepared(clean, preparation)
        except (SpyActionsDisabled, SpyRequestRejected) as exc:
            self.database.finish_spy_action(request_id, status="failed_safe", detail=str(exc))
            raise
        except Exception as exc:
            # After pending is committed, uncertainty can never open an automatic retry window.
            self.database.finish_spy_action(request_id, status="ambiguous", detail=str(exc))
            raise

        self.database.finish_spy_action(
            request_id,
            status="verified" if result.verified else "ambiguous",
            report_id=result.report_id,
            requested_at=self._iso(result.requested_at),
            report_at=self._iso(result.report_at),
            detail=result.detail,
        )
        return result

    def _begin(self, request_id: str, preparation: SpyRequestPreparation) -> None:
        try:
            self.database.begin_spy_action(
                request_id=request_id,
                fleet_id=preparation.fleet_id,
                source=preparation.source,
                target=preparation.target,
            )
        except V2DatabaseError as exc:
            raise SpyRequestBlocked(str(exc)) from exc

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    @staticmethod
    def _record_from_row(row: dict[str, object]) -> SpyActionRecord:
        return SpyActionRecord(
            request_id=str(row["request_id"]),
            fleet_id=str(row["fleet_id"]) if row.get("fleet_id") is not None else None,
            source=str(row["source"]),
            target=str(row["target"]),
            status=str(row["status"]),
            report_id=str(row["report_id"]) if row.get("report_id") is not None else None,
            requested_at=str(row["requested_at"]) if row.get("requested_at") is not None else None,
            report_at=str(row["report_at"]) if row.get("report_at") is not None else None,
            created_at=str(row["created_at"]),
            detail=str(row.get("detail") or ""),
        )

    def record(self, request_id: str) -> SpyActionRecord | None:
        row = self.database.read_spy_action(request_id)
        return None if row is None else self._record_from_row(row)

    def recent(self, *, limit: int = 200) -> list[SpyActionRecord]:
        return [self._record_from_row(row) for row in self.database.list_spy_actions(limit=limit)]

    def resolve_verified(
        self,
        request_id: str,
        *,
        report_id: str,
        report_at: datetime,
    ) -> SpyActionRecord:
        if report_at.tzinfo is None:
            raise SpyActionError("report_at must be timezone-aware")
        self.database.resolve_spy_action(
            request_id,
            report_id=report_id,
            report_at=report_at.isoformat(),
        )
        record = self.record(request_id)
        if record is None:
            raise SpyActionError(f"Resolved spy request disappeared: {request_id}")
        return record
