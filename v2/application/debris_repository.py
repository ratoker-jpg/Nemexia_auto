from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from v2.application.debris_source import DebrisReadSnapshot
from v2.domain.debris import DEBRIS_CANONICAL_MARKER, DebrisObservationFact, DebrisReadState
from v2.domain.debris_candidates import (
    DebrisCandidatePreview,
    DebrisCandidateDecision,
    build_debris_candidate_preview,
    debris_observation_identity,
)
from v2.domain.asteroids import AsteroidObservationFact
from v2.persistence.database import V2Database
from v2.persistence.debris_candidates import DebrisObservationRepository


@dataclass(frozen=True)
class DebrisIngestResult:
    inserted: int
    exact_duplicates: int
    preview: DebrisCandidatePreview


class V2DebrisRepository:
    """Append-only V2-owned debris evidence and deterministic candidate projection."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        self.storage = DebrisObservationRepository(database)

    @staticmethod
    def _parse_time(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _fact_from_row(cls, row: dict[str, object]) -> DebrisObservationFact:
        asteroid = AsteroidObservationFact(
            galaxy=int(row["galaxy"]),
            system=int(row["system"]),
            position=int(row["position"]),
            last_move_at=cls._parse_time(row["last_move_at"]),
            next_move_at=cls._parse_time(row["next_move_at"]),
            period_seconds=int(row["period_seconds"]),
            observed_at=cls._parse_time(row["observed_at"]),
            source=str(row.get("evidence_source") or "galaxy.squareInfo"),
        )
        return DebrisObservationFact(
            asteroid=asteroid,
            marker=str(row.get("marker") or DEBRIS_CANONICAL_MARKER),
            source=str(row.get("evidence_source") or "galaxy.squareInfo"),
        )

    @staticmethod
    def _row_from_fact(fact: DebrisObservationFact) -> dict[str, object]:
        asteroid = fact.asteroid
        return {
            "galaxy": asteroid.galaxy,
            "system": asteroid.system,
            "position": asteroid.position,
            "last_move_at": asteroid.last_move_at.isoformat(),
            "next_move_at": asteroid.next_move_at.isoformat(),
            "period_seconds": asteroid.period_seconds,
            "observed_at": asteroid.observed_at.isoformat(),
            "evidence_source": fact.source,
            "marker": fact.marker,
        }

    def observations(self, *, limit: int | None = None) -> tuple[DebrisObservationFact, ...]:
        return tuple(self._fact_from_row(row) for row in self.storage.list(limit=limit))

    def preview(
        self,
        incoming: Iterable[DebrisObservationFact] = (),
        *,
        now: datetime,
    ) -> DebrisCandidatePreview:
        return build_debris_candidate_preview(
            persisted=self.observations(),
            incoming=tuple(incoming),
            now=now,
        )

    def ingest(
        self,
        incoming: Iterable[DebrisObservationFact],
        *,
        now: datetime,
    ) -> DebrisIngestResult:
        incoming = tuple(incoming)
        existing_ids = self.storage.identities()
        preview = build_debris_candidate_preview(
            persisted=self.observations(),
            incoming=incoming,
            now=now,
        )
        rejected_ids = {
            debris_observation_identity(item.observation)
            for item in preview.decisions
            if item.current_coord is None
            and item.decision in {DebrisCandidateDecision.SKIP_INVALID, DebrisCandidateDecision.SKIP_OUT_OF_RANGE}
        }
        rows: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        exact_duplicates = 0
        for fact in incoming:
            identity = debris_observation_identity(fact)
            storage_identity = tuple(self.storage.canonical_row(self._row_from_fact(fact)))
            if storage_identity in existing_ids or identity in seen:
                exact_duplicates += 1
                continue
            seen.add(identity)
            if identity in rejected_ids:
                continue
            rows.append(self._row_from_fact(fact))
        inserted = self.storage.insert(rows)
        return DebrisIngestResult(inserted, exact_duplicates, preview)

    def ingest_read(self, snapshot: DebrisReadSnapshot, *, now: datetime) -> DebrisIngestResult:
        """Persist only a fully proven current-system read.

        `no_debris` is intentionally a no-op: without an approved full 120-system
        traversal it has no authority to delete evidence captured elsewhere.
        """

        if snapshot.state is DebrisReadState.NO_DEBRIS:
            return DebrisIngestResult(0, 0, self.preview(now=now))
        if snapshot.state is not DebrisReadState.READY:
            raise ValueError(f"Cannot ingest incomplete debris read: {snapshot.state.value}")
        return self.ingest(snapshot.observations, now=now)
