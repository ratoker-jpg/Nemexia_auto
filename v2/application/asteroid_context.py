from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidActionRecord, AsteroidRequestCoordinator
from v2.application.asteroid_repository import AsteroidIngestResult, V2AsteroidRepository
from v2.application.asteroid_source import AsteroidReadSnapshot, V2AsteroidSource
from v2.application.asteroid_workflow import (
    AsteroidDispatchBatch,
    AsteroidPreparationBatch,
    dispatch_selected_asteroids,
    prepare_selected_asteroids,
)
from v2.application.recon_context import ReconOwnedApplicationContext
from v2.domain.asteroid_candidates import AsteroidCandidate, AsteroidCandidatePreview
from v2.domain.asteroids import AsteroidObservationFact


class AsteroidEnabledApplicationContext(ReconOwnedApplicationContext):
    """Expose explicit manual asteroid observation/prepare/dispatch operations only."""

    def __init__(
        self,
        *args,
        asteroid_source: V2AsteroidSource,
        asteroid_actions: AsteroidActionService,
        asteroid_repository: V2AsteroidRepository | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._asteroid_source = asteroid_source
        self._asteroid_actions = asteroid_actions
        database = getattr(self, "_v2_database", None)
        self._asteroid_repository = asteroid_repository or (
            V2AsteroidRepository(database) if database is not None else None
        )

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        parsed = super().set_v2_settings(values)
        if "actions_enabled" in parsed:
            self._asteroid_actions.set_enabled(bool(parsed["actions_enabled"]))
        return parsed

    def asteroid_actions_enabled(self) -> bool:
        return bool(self._asteroid_actions.enabled)

    def live_asteroids(self) -> AsteroidReadSnapshot:
        return self._asteroid_source.read()

    def asteroid_candidates(self, *, now: datetime | None = None) -> AsteroidCandidatePreview:
        if self._asteroid_repository is None:
            raise RuntimeError("V2 asteroid candidate storage is unavailable")
        return self._asteroid_repository.preview(now=now or datetime.now(timezone.utc))

    def ingest_asteroid_observations(
        self,
        observations: Sequence[AsteroidObservationFact],
        *,
        now: datetime | None = None,
    ) -> AsteroidIngestResult:
        if self._asteroid_repository is None:
            raise RuntimeError("V2 asteroid candidate storage is unavailable")
        return self._asteroid_repository.ingest(
            tuple(observations),
            now=now or datetime.now(timezone.utc),
        )

    @staticmethod
    def _command(
        *,
        source: str,
        observation: AsteroidObservationFact,
        recycler_count: int,
        safety_seconds: int,
    ) -> AsteroidDispatchCommand:
        return AsteroidDispatchCommand(
            source=str(source),
            observation=observation,
            recycler_count=int(recycler_count),
            safety_seconds=int(safety_seconds),
        )

    def prepare_asteroid(
        self,
        *,
        source: str,
        observation: AsteroidObservationFact,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> AsteroidDispatchPreparation:
        return self._asteroid_actions.prepare(
            self._command(
                source=source,
                observation=observation,
                recycler_count=recycler_count,
                safety_seconds=safety_seconds,
            )
        )

    def dispatch_asteroid(
        self,
        *,
        source: str,
        observation: AsteroidObservationFact,
        recycler_count: int,
        safety_seconds: int = 10,
        request_id: str,
    ) -> AsteroidDispatchResult:
        database = getattr(self, "_v2_database", None)
        if database is None:
            raise RuntimeError("V2 asteroid journal is unavailable")
        command = self._command(
            source=source,
            observation=observation,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )
        return AsteroidRequestCoordinator(self._asteroid_actions, database).dispatch(
            command,
            request_id=str(request_id),
        )

    def asteroid_action_record(self, request_id: str) -> AsteroidActionRecord | None:
        database = getattr(self, "_v2_database", None)
        if database is None:
            return None
        return AsteroidRequestCoordinator(self._asteroid_actions, database).record(request_id)

    def prepare_asteroid_candidates(
        self,
        candidates: Sequence[AsteroidCandidate],
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> AsteroidPreparationBatch:
        return prepare_selected_asteroids(
            self,
            candidates,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )

    def dispatch_asteroid_candidates(
        self,
        candidates: Sequence[AsteroidCandidate],
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
        should_stop: Callable[[], bool] | None = None,
    ) -> AsteroidDispatchBatch:
        return dispatch_selected_asteroids(
            self,
            candidates,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
            should_stop=should_stop,
        )

    def recent_asteroid_actions(self, *, limit: int = 200) -> list[AsteroidActionRecord]:
        database = getattr(self, "_v2_database", None)
        if database is None:
            return []
        return AsteroidRequestCoordinator(self._asteroid_actions, database).recent(limit=limit)

    def close(self) -> None:
        actions = getattr(self, "_asteroid_actions", None)
        if actions is not None:
            actions.close()
            self._asteroid_actions = None
        self._asteroid_repository = None
        super().close()
