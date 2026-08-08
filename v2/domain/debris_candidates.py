from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from v2.domain.asteroid_candidates import observation_identity
from v2.domain.asteroids import predict_coordinate
from v2.domain.debris import DebrisObservationFact


class DebrisCandidateDecision(str, Enum):
    ADD = "add"
    KEEP = "keep"
    SKIP_DUPLICATE = "skip_duplicate"
    SKIP_INVALID = "skip_invalid"
    SKIP_OUT_OF_RANGE = "skip_out_of_range"


@dataclass(frozen=True)
class DebrisCandidate:
    observation: DebrisObservationFact
    current_galaxy: int
    current_system: int
    current_position: int
    shifts: int
    persisted: bool

    @property
    def current_coord(self) -> str:
        return f"{self.current_galaxy}:{self.current_system}:{self.current_position}"


@dataclass(frozen=True)
class DebrisCandidateDecisionFact:
    decision: DebrisCandidateDecision
    observation: DebrisObservationFact
    current_coord: str | None
    detail: str


@dataclass(frozen=True)
class DebrisCandidatePreview:
    candidates: tuple[DebrisCandidate, ...]
    decisions: tuple[DebrisCandidateDecisionFact, ...]

    @property
    def added(self) -> int:
        return sum(item.decision is DebrisCandidateDecision.ADD for item in self.decisions)

    @property
    def kept(self) -> int:
        return sum(item.decision is DebrisCandidateDecision.KEEP for item in self.decisions)

    @property
    def skipped(self) -> int:
        return len(self.decisions) - self.added - self.kept


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def debris_observation_identity(observation: DebrisObservationFact) -> tuple[object, ...]:
    return observation_identity(observation.asteroid) + (
        str(observation.source or "galaxy.squareInfo"),
        str(observation.marker),
    )


def _candidate(
    observation: DebrisObservationFact,
    *,
    now: datetime,
    persisted: bool,
) -> DebrisCandidate:
    if not observation.structurally_valid:
        raise ValueError("invalid debris observation")
    current, shifts = predict_coordinate(observation.asteroid, _utc(now), safety_seconds=0)
    return DebrisCandidate(
        observation=observation,
        current_galaxy=current[0],
        current_system=current[1],
        current_position=current[2],
        shifts=shifts,
        persisted=persisted,
    )


def build_debris_candidate_preview(
    *,
    persisted: Iterable[DebrisObservationFact],
    incoming: Iterable[DebrisObservationFact],
    now: datetime,
) -> DebrisCandidatePreview:
    """Project immutable debris evidence to current coordinates deterministically."""

    now = _utc(now)
    persisted_items = tuple(persisted)
    incoming_items = tuple(incoming)
    accepted: list[DebrisCandidate] = []
    decisions: list[DebrisCandidateDecisionFact] = []
    seen_evidence: set[tuple[object, ...]] = set()

    for is_persisted, observations in ((True, persisted_items), (False, incoming_items)):
        for observation in observations:
            identity = debris_observation_identity(observation)
            if identity in seen_evidence:
                if not is_persisted:
                    decisions.append(DebrisCandidateDecisionFact(
                        DebrisCandidateDecision.SKIP_DUPLICATE,
                        observation,
                        None,
                        "Exact debris evidence is already stored or repeated",
                    ))
                continue
            seen_evidence.add(identity)
            if not observation.structurally_valid:
                decisions.append(DebrisCandidateDecisionFact(
                    DebrisCandidateDecision.SKIP_INVALID,
                    observation,
                    None,
                    "Debris evidence is structurally invalid",
                ))
                continue
            try:
                accepted.append(_candidate(observation, now=now, persisted=is_persisted))
            except ValueError as exc:
                decisions.append(DebrisCandidateDecisionFact(
                    DebrisCandidateDecision.SKIP_OUT_OF_RANGE,
                    observation,
                    None,
                    str(exc),
                ))

    groups: dict[str, list[DebrisCandidate]] = {}
    for item in accepted:
        groups.setdefault(item.current_coord, []).append(item)

    selected: list[DebrisCandidate] = []
    for coord, group in groups.items():
        group.sort(key=lambda item: (
            -_utc(item.observation.asteroid.observed_at).timestamp(),
            0 if item.persisted else 1,
            debris_observation_identity(item.observation),
        ))
        winner = group[0]
        selected.append(winner)
        decisions.append(DebrisCandidateDecisionFact(
            DebrisCandidateDecision.KEEP if winner.persisted else DebrisCandidateDecision.ADD,
            winner.observation,
            coord,
            "Selected freshest proven debris evidence for current coordinate",
        ))
        for duplicate in group[1:]:
            decisions.append(DebrisCandidateDecisionFact(
                DebrisCandidateDecision.SKIP_DUPLICATE,
                duplicate.observation,
                coord,
                "Fresher debris evidence represents the same current coordinate",
            ))

    selected.sort(key=lambda item: (
        item.current_galaxy,
        -item.current_system,
        item.current_position,
        -_utc(item.observation.asteroid.observed_at).timestamp(),
        debris_observation_identity(item.observation),
    ))
    decisions.sort(key=lambda item: (
        item.current_coord or "999:999:999",
        item.decision.value,
        debris_observation_identity(item.observation),
    ))
    return DebrisCandidatePreview(tuple(selected), tuple(decisions))
