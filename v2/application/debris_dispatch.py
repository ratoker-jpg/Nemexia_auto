from __future__ import annotations

from dataclasses import dataclass

from v2.application.asteroid_actions import (
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidActionRecord, AsteroidRequestCoordinator
from v2.domain.debris_candidates import DebrisCandidate


@dataclass(frozen=True)
class DebrisDispatchPreparation:
    """Typed debris view of the authoritative asteroid preparation."""

    candidate: DebrisCandidate
    asteroid: AsteroidDispatchPreparation

    @property
    def target(self) -> str:
        return self.asteroid.target

    @property
    def movement_margin_seconds(self) -> float:
        return self.asteroid.movement_margin_seconds


def asteroid_command_from_debris(
    candidate: DebrisCandidate,
    *,
    source: str,
    recycler_count: int,
    safety_seconds: int = 10,
) -> AsteroidDispatchCommand:
    """Map debris discovery provenance onto the single asteroid mutation command.

    Debris changes discovery/evidence only. The remote side effect is still the
    recycler asteroid mission, so the command carries the exact immutable
    asteroid observation and deliberately contains no debris label or second
    action identity.
    """

    if not isinstance(candidate, DebrisCandidate) or not candidate.observation.structurally_valid:
        raise ValueError("A proven debris candidate is required")
    return AsteroidDispatchCommand(
        source=str(source),
        observation=candidate.observation.asteroid,
        recycler_count=int(recycler_count),
        safety_seconds=int(safety_seconds),
    )


class DebrisDispatchReuseGate:
    """Reuse the authoritative asteroid service + ``asteroid_actions`` journal.

    This class owns no browser backend and no journal. It is intentionally a
    typed adapter around ``AsteroidRequestCoordinator`` so unresolved trajectory
    identity, live preparation, exactly-one SendFleet and exact new-flight
    verification stay authoritative in one place.
    """

    def __init__(self, coordinator: AsteroidRequestCoordinator) -> None:
        self.coordinator = coordinator

    def command(
        self,
        candidate: DebrisCandidate,
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> AsteroidDispatchCommand:
        return asteroid_command_from_debris(
            candidate,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )

    def prepare(
        self,
        candidate: DebrisCandidate,
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
    ) -> DebrisDispatchPreparation:
        command = self.command(
            candidate,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )
        prepared = self.coordinator.service.prepare(command)
        if prepared.observation != candidate.observation.asteroid:
            raise RuntimeError("Debris preparation lost immutable asteroid provenance")
        return DebrisDispatchPreparation(candidate, prepared)

    def dispatch(
        self,
        candidate: DebrisCandidate,
        *,
        source: str,
        recycler_count: int,
        safety_seconds: int = 10,
        request_id: str,
    ) -> AsteroidDispatchResult:
        command = self.command(
            candidate,
            source=source,
            recycler_count=recycler_count,
            safety_seconds=safety_seconds,
        )
        return self.coordinator.dispatch(command, request_id=str(request_id))

    def record(self, request_id: str) -> AsteroidActionRecord | None:
        return self.coordinator.record(str(request_id))
