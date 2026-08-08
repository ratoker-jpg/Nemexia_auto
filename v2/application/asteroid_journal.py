from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from v2.application.asteroid_actions import (
    AsteroidActionError,
    AsteroidActionService,
    AsteroidActionsDisabled,
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchRejected,
    AsteroidDispatchResult,
    AsteroidPreparationRejected,
    validate_command,
    validate_fleet_id,
)
from v2.persistence.asteroid_journal import AsteroidJournalRepository
from v2.persistence.database import V2Database, V2DatabaseError


class AsteroidRequestBlocked(AsteroidActionError):
    """An immutable asteroid request is already resolved or remains unresolved."""


@dataclass(frozen=True)
class AsteroidActionRecord:
    request_id: str
    source: str
    observation_coord: str
    observation_next_move_at: str
    target: str
    recycler_count: int
    status: str
    fleet_id: str | None
    sent_at: str | None
    arrival_at: str | None
    return_at: str | None
    created_at: str
    detail: str


class AsteroidRequestCoordinator:
    """Persist asteroid intent before exactly one future remote SendFleet attempt."""

    def __init__(self, service: AsteroidActionService, database: V2Database) -> None:
        self.service = service
        self.database = database
        self.journal = AsteroidJournalRepository(database)

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        *,
        request_id: str,
    ) -> AsteroidDispatchResult:
        clean = validate_command(command)
        request_id = str(request_id or "").strip()
        if not request_id:
            raise AsteroidRequestBlocked("request_id is required")
        if not self.service.enabled:
            raise AsteroidActionsDisabled("V2 asteroid actions are disabled")

        existing = self.journal.read(request_id)
        if existing is not None:
            raise AsteroidRequestBlocked(
                f"Asteroid request {request_id} already exists with status {existing['status']}"
            )

        # Preparation is read-only. It must complete before the journal creates
        # immutable pending intent, while no remote SendFleet has been attempted.
        preparation = self.service.prepare(clean)
        unresolved = self.journal.unresolved(
            source=preparation.source,
            observation_coord=preparation.observation.coord,
            observation_next_move_at=self._identity_iso(preparation.observation.next_move_at),
            target=preparation.target,
        )
        if unresolved is not None:
            raise AsteroidRequestBlocked(
                "Есть незавершённая или неоднозначная отправка на этот asteroid trajectory: "
                f"{unresolved['request_id']} · {unresolved['status']}"
            )

        self._begin(request_id, clean, preparation)

        try:
            result = self.service.dispatch_prepared(clean, preparation)
        except (
            AsteroidActionsDisabled,
            AsteroidCaptchaBlocked,
            AsteroidPreparationRejected,
            AsteroidDispatchRejected,
        ) as exc:
            # These exception types are reserved for conditions where the backend
            # has positively proved no remote fleet was accepted.
            self.journal.finish(
                request_id,
                status="failed_safe",
                detail=str(exc),
            )
            raise
        except AsteroidDispatchAmbiguous as exc:
            # Preserve every structured fact the backend managed to observe. The
            # row stays unresolved, so this evidence never opens a retry window.
            evidence = exc.result
            detail_parts = [str(exc)]
            if evidence is not None and evidence.server_info:
                detail_parts.append(str(evidence.server_info))
            self.journal.finish(
                request_id,
                status="ambiguous",
                fleet_id=evidence.fleet_id if evidence is not None else None,
                sent_at=self._iso(evidence.sent_at) if evidence is not None else None,
                arrival_at=self._iso(evidence.arrival_at) if evidence is not None else None,
                return_at=self._iso(evidence.return_at) if evidence is not None else None,
                detail=" | ".join(part for part in detail_parts if part),
            )
            raise
        except Exception as exc:
            # Once pending exists, every unclassified failure is conservative:
            # the remote effect may have happened, so no automatic retry window.
            self.journal.finish(
                request_id,
                status="ambiguous",
                detail=str(exc),
            )
            raise

        self.journal.finish(
            request_id,
            status="verified" if result.verified else "ambiguous",
            fleet_id=result.fleet_id,
            sent_at=self._iso(result.sent_at),
            arrival_at=self._iso(result.arrival_at),
            return_at=self._iso(result.return_at),
            detail=result.server_info,
        )
        return result

    def _begin(
        self,
        request_id: str,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> None:
        observation = preparation.observation
        try:
            self.journal.begin(
                request_id=request_id,
                source=preparation.source,
                observation_coord=observation.coord,
                observation_last_move_at=self._identity_iso(observation.last_move_at),
                observation_next_move_at=self._identity_iso(observation.next_move_at),
                observation_period_seconds=observation.period_seconds,
                observation_observed_at=self._identity_iso(observation.observed_at),
                target=preparation.target,
                recycler_count=preparation.recycler_count,
                safety_seconds=command.safety_seconds,
                prepared_at=self._identity_iso(preparation.prepared_at),
                one_way_seconds=preparation.one_way_seconds,
                round_trip_seconds=preparation.round_trip_seconds,
                shifts=preparation.shifts,
                gas_needed=preparation.gas_needed,
            )
        except V2DatabaseError as exc:
            raise AsteroidRequestBlocked(str(exc)) from exc

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    @staticmethod
    def _identity_iso(value: datetime) -> str:
        # Asteroid domain comparisons treat naive values as UTC; journal identity
        # must use the same canonical instant or offset variants could bypass the
        # partial unique index after an ambiguous side effect.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _record_from_row(row: dict[str, object]) -> AsteroidActionRecord:
        return AsteroidActionRecord(
            request_id=str(row["request_id"]),
            source=str(row["source"]),
            observation_coord=str(row["observation_coord"]),
            observation_next_move_at=str(row["observation_next_move_at"]),
            target=str(row["target"]),
            recycler_count=int(row["recycler_count"]),
            status=str(row["status"]),
            fleet_id=str(row["fleet_id"]) if row.get("fleet_id") is not None else None,
            sent_at=str(row["sent_at"]) if row.get("sent_at") is not None else None,
            arrival_at=str(row["arrival_at"]) if row.get("arrival_at") is not None else None,
            return_at=str(row["return_at"]) if row.get("return_at") is not None else None,
            created_at=str(row["created_at"]),
            detail=str(row.get("detail") or ""),
        )

    def record(self, request_id: str) -> AsteroidActionRecord | None:
        row = self.journal.read(request_id)
        return None if row is None else self._record_from_row(row)

    def recent(self, *, limit: int = 200) -> list[AsteroidActionRecord]:
        return [self._record_from_row(row) for row in self.journal.list(limit=limit)]

    def resolve_verified(
        self,
        request_id: str,
        *,
        fleet_id: str,
        sent_at: datetime | None = None,
        arrival_at: datetime | None = None,
        return_at: datetime | None = None,
    ) -> AsteroidActionRecord:
        fleet_id = validate_fleet_id(fleet_id)
        for name, value in (
            ("sent_at", sent_at),
            ("arrival_at", arrival_at),
            ("return_at", return_at),
        ):
            if value is not None and value.tzinfo is None:
                raise AsteroidActionError(f"{name} must be timezone-aware")
        self.journal.resolve_verified(
            request_id,
            fleet_id=fleet_id,
            sent_at=self._iso(sent_at),
            arrival_at=self._iso(arrival_at),
            return_at=self._iso(return_at),
        )
        record = self.record(request_id)
        if record is None:
            raise AsteroidActionError(f"Resolved asteroid request disappeared: {request_id}")
        return record
