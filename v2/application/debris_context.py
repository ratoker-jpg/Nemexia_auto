from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Sequence

from v2.application.asteroid_context import AsteroidEnabledApplicationContext
from v2.application.asteroid_journal import AsteroidRequestCoordinator
from v2.application.debris_dispatch import DebrisDispatchReuseGate
from v2.application.debris_repository import DebrisIngestResult, V2DebrisRepository
from v2.application.debris_source import DebrisReadSnapshot, V2DebrisSource
from v2.application.debris_workflow import (
    DebrisDispatchBatch,
    DebrisPreparationBatch,
    DebrisWorkflowController,
)
from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.domain.debris_candidates import DebrisCandidate, DebrisCandidatePreview
from v2.persistence.navigation_journal import NavigationJournalRecord


class DebrisEnabledApplicationContext(AsteroidEnabledApplicationContext):
    """Expose controlled debris reads/evidence/workflow over the shared asteroid mutation boundary."""

    def __init__(
        self,
        *args,
        debris_source: V2DebrisSource,
        debris_repository: V2DebrisRepository | None = None,
        navigation_coordinator: NavigationCoordinator | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._debris_source = debris_source
        self._navigation_coordinator = navigation_coordinator
        database = getattr(self, "_v2_database", None)
        self._debris_repository = debris_repository or (
            V2DebrisRepository(database) if database is not None else None
        )
        if database is None:
            self._debris_gate = None
            self._debris_workflow = None
        else:
            # This is deliberately the same action service and the same V2 DB used
            # by generic asteroid dispatch. Debris gets no second SendFleet/journal.
            coordinator = AsteroidRequestCoordinator(self._asteroid_actions, database)
            self._debris_gate = DebrisDispatchReuseGate(coordinator)
            self._debris_workflow = DebrisWorkflowController(self._debris_gate)

    def navigation_observation(self) -> NavigationObservation | None:
        if self._navigation_coordinator is None:
            return None
        return self._navigation_coordinator.observe()

    def recent_navigation_actions(self, *, limit: int = 200) -> tuple[NavigationJournalRecord, ...]:
        if self._navigation_coordinator is None:
            return ()
        return self._navigation_coordinator.recent(limit=limit)

    def unresolved_navigation_actions(self) -> tuple[NavigationJournalRecord, ...]:
        if self._navigation_coordinator is None:
            return ()
        return self._navigation_coordinator.unresolved()

    def debris_actions_enabled(self) -> bool:
        return self.asteroid_actions_enabled()

    def live_debris(self) -> DebrisReadSnapshot:
        return self._debris_source.read()

    def debris_candidates(self, *, now: datetime | None = None) -> DebrisCandidatePreview:
        if self._debris_repository is None:
            raise RuntimeError("V2 debris evidence storage is unavailable")
        return self._debris_repository.preview(now=now or datetime.now(timezone.utc))

    def ingest_debris_read(
        self,
        snapshot: DebrisReadSnapshot,
        *,
        now: datetime | None = None,
    ) -> DebrisIngestResult:
        if self._debris_repository is None:
            raise RuntimeError("V2 debris evidence storage is unavailable")
        return self._debris_repository.ingest_read(
            snapshot,
            now=now or datetime.now(timezone.utc),
        )

    def prepare_debris_candidates(
        self,
        candidates: Sequence[DebrisCandidate],
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> DebrisPreparationBatch:
        if self._debris_workflow is None:
            raise RuntimeError("V2 debris workflow is unavailable")
        return self._debris_workflow.prepare(
            candidates,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )

    def confirm_debris_candidates(
        self,
        confirmation_id: str,
        *,
        between_attempts: Callable[[], None] | None = None,
    ) -> DebrisDispatchBatch:
        if self._debris_workflow is None:
            raise RuntimeError("V2 debris workflow is unavailable")
        return self._debris_workflow.confirm_and_dispatch(
            confirmation_id,
            between_attempts=between_attempts,
        )

    def request_debris_stop(self) -> None:
        if self._debris_workflow is not None:
            self._debris_workflow.request_stop()

    def cancel_debris_preparation(self) -> None:
        """Disarm an unconfirmed debris batch without touching browser/journal state."""
        if self._debris_workflow is not None:
            self._debris_workflow.cancel_prepared()

    def close(self) -> None:
        workflow = getattr(self, "_debris_workflow", None)
        if workflow is not None:
            # Closing the window/context may happen after preparation or between
            # verified attempts. Never cancel a started remote attempt; only stop
            # the next one and disarm any still-unconfirmed batch.
            workflow.request_stop()
            workflow.cancel_prepared()

        source = getattr(self, "_debris_source", None)
        if source is not None:
            close = getattr(source, "close", None)
            if callable(close):
                close()
            self._debris_source = None
        navigation = getattr(self, "_navigation_coordinator", None)
        if navigation is not None:
            navigation.close()
            self._navigation_coordinator = None
        self._debris_repository = None
        self._debris_workflow = None
        self._debris_gate = None
        super().close()
