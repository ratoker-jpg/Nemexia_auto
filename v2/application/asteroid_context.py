from __future__ import annotations

from typing import Mapping

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidActionRecord, AsteroidRequestCoordinator
from v2.application.asteroid_source import AsteroidReadSnapshot, V2AsteroidSource
from v2.application.recon_context import ReconOwnedApplicationContext
from v2.domain.asteroids import AsteroidObservationFact


class AsteroidEnabledApplicationContext(ReconOwnedApplicationContext):
    """Expose explicit manual asteroid observation/prepare/dispatch operations only."""

    def __init__(
        self,
        *args,
        asteroid_source: V2AsteroidSource,
        asteroid_actions: AsteroidActionService,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._asteroid_source = asteroid_source
        self._asteroid_actions = asteroid_actions

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        parsed = super().set_v2_settings(values)
        if "actions_enabled" in parsed:
            self._asteroid_actions.set_enabled(bool(parsed["actions_enabled"]))
        return parsed

    def asteroid_actions_enabled(self) -> bool:
        return bool(self._asteroid_actions.enabled)

    def live_asteroids(self) -> AsteroidReadSnapshot:
        return self._asteroid_source.read()

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
        super().close()
