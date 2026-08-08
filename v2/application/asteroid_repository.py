from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from v2.domain.asteroid_candidates import (
    AsteroidCandidatePreview,
    build_candidate_preview,
    observation_identity,
)
from v2.domain.asteroids import AsteroidObservationFact
from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.database import V2Database


@dataclass(frozen=True)
class AsteroidIngestResult:
    inserted: int
    exact_duplicates: int
    preview: AsteroidCandidatePreview


class V2AsteroidRepository:
    """V2-owned immutable asteroid observations + deterministic candidate view."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        self.storage = AsteroidObservationRepository(database)

    @staticmethod
    def _parse_time(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _fact_from_row(cls, row: dict[str, object]) -> AsteroidObservationFact:
        return AsteroidObservationFact(
            galaxy=int(row["galaxy"]),
            system=int(row["system"]),
            position=int(row["position"]),
            last_move_at=cls._parse_time(row["last_move_at"]),
            next_move_at=cls._parse_time(row["next_move_at"]),
            period_seconds=int(row["period_seconds"]),
            observed_at=cls._parse_time(row["observed_at"]),
            source=str(row.get("source") or "galaxy.squareInfo"),
        )

    @staticmethod
    def _row_from_fact(fact: AsteroidObservationFact) -> dict[str, object]:
        identity = observation_identity(fact)
        return {
            "galaxy": identity[0],
            "system": identity[1],
            "position": identity[2],
            "last_move_at": identity[3],
            "next_move_at": identity[4],
            "period_seconds": identity[5],
            "observed_at": identity[6],
            "source": identity[7],
        }

    def observations(self, *, limit: int = 5000) -> tuple[AsteroidObservationFact, ...]:
        return tuple(self._fact_from_row(row) for row in self.storage.list(limit=limit))

    def preview(
        self,
        incoming: Iterable[AsteroidObservationFact] = (),
        *,
        now: datetime,
    ) -> AsteroidCandidatePreview:
        return build_candidate_preview(
            persisted=self.observations(),
            incoming=tuple(incoming),
            now=now,
        )

    def ingest(
        self,
        incoming: Iterable[AsteroidObservationFact],
        *,
        now: datetime,
    ) -> AsteroidIngestResult:
        incoming = tuple(incoming)
        existing_ids = self.storage.identities()
        preview = build_candidate_preview(
            persisted=self.observations(),
            incoming=incoming,
            now=now,
        )

        # Persist every unique proven observation that remains predictably inside
        # the supported 1..40 system range. Candidate dedupe is a separate view;
        # provenance is not thrown away merely because fresher evidence wins.
        rejected_ids = {
            observation_identity(item.observation)
            for item in preview.decisions
            if item.current_coord is None
            and item.decision.value in {"skip_invalid", "skip_out_of_range"}
        }
        unique_rows: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        exact_duplicates = 0
        for fact in incoming:
            identity = observation_identity(fact)
            if identity in existing_ids or identity in seen:
                exact_duplicates += 1
                continue
            seen.add(identity)
            if identity in rejected_ids:
                continue
            unique_rows.append(self._row_from_fact(fact))
        inserted = self.storage.insert(unique_rows)
        return AsteroidIngestResult(
            inserted=inserted,
            exact_duplicates=exact_duplicates,
            # Keep the operation diff: recomputing after persistence would turn
            # ADD into KEEP and would erase rejected incoming decisions entirely.
            preview=preview,
        )
