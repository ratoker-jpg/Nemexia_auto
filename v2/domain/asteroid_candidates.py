from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from v2.domain.asteroids import AsteroidObservationFact, predict_coordinate


class AsteroidCandidateDecision(str, Enum):
    ADD = "add"
    KEEP = "keep"
    SKIP_DUPLICATE = "skip_duplicate"
    SKIP_INVALID = "skip_invalid"
    SKIP_OUT_OF_RANGE = "skip_out_of_range"


@dataclass(frozen=True)
class AsteroidCandidate:
    observation: AsteroidObservationFact
    current_galaxy: int
    current_system: int
    current_position: int
    shifts: int
    persisted: bool

    @property
    def current_coord(self) -> str:
        return f"{self.current_galaxy}:{self.current_system}:{self.current_position}"


@dataclass(frozen=True)
class AsteroidCandidateDecisionFact:
    decision: AsteroidCandidateDecision
    observation: AsteroidObservationFact
    current_coord: str | None
    detail: str


@dataclass(frozen=True)
class AsteroidCandidatePreview:
    candidates: tuple[AsteroidCandidate, ...]
    decisions: tuple[AsteroidCandidateDecisionFact, ...]

    @property
    def added(self) -> int:
        return sum(item.decision is AsteroidCandidateDecision.ADD for item in self.decisions)

    @property
    def kept(self) -> int:
        return sum(item.decision is AsteroidCandidateDecision.KEEP for item in self.decisions)

    @property
    def skipped(self) -> int:
        return len(self.decisions) - self.added - self.kept


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def observation_identity(observation: AsteroidObservationFact) -> tuple[object, ...]:
    """Canonical immutable evidence identity, independent of timezone spelling."""

    return (
        int(observation.galaxy),
        int(observation.system),
        int(observation.position),
        _utc(observation.last_move_at).isoformat(),
        _utc(observation.next_move_at).isoformat(),
        int(observation.period_seconds),
        _utc(observation.observed_at).isoformat(),
        str(observation.source or "galaxy.squareInfo"),
    )


def _candidate(
    observation: AsteroidObservationFact,
    *,
    now: datetime,
    persisted: bool,
) -> AsteroidCandidate:
    if not observation.structurally_valid:
        raise ValueError("invalid observation")
    current, shifts = predict_coordinate(observation, _utc(now), safety_seconds=0)
    return AsteroidCandidate(
        observation=observation,
        current_galaxy=current[0],
        current_system=current[1],
        current_position=current[2],
        shifts=shifts,
        persisted=persisted,
    )


def _candidate_preference(item: AsteroidCandidate) -> tuple[object, ...]:
    # Freshest evidence wins for one predicted current coordinate. Exact ties
    # prefer already persisted evidence, then use the immutable identity.
    return (
        -_utc(item.observation.observed_at).timestamp(),
        0 if item.persisted else 1,
        observation_identity(item.observation),
    )


def _candidate_order(item: AsteroidCandidate) -> tuple[object, ...]:
    # Effective legacy discovery scans systems from high to low. Make that order
    # explicit and deterministic without depending on browser/DOM order.
    return (
        item.current_galaxy,
        -item.current_system,
        item.current_position,
        -_utc(item.observation.observed_at).timestamp(),
        observation_identity(item.observation),
    )


def build_candidate_preview(
    *,
    persisted: Iterable[AsteroidObservationFact],
    incoming: Iterable[AsteroidObservationFact],
    now: datetime,
) -> AsteroidCandidatePreview:
    """Pure candidate/diff policy over immutable observation facts.

    There is deliberately no age TTL. A proven movement trajectory may remain
    usable until deterministic prediction leaves system 40 or new evidence
    contradicts it in a later read/pre-send stage.
    """

    now = _utc(now)
    persisted_items = tuple(persisted)
    incoming_items = tuple(incoming)
    persisted_ids = {observation_identity(item) for item in persisted_items}

    accepted: list[AsteroidCandidate] = []
    decisions: list[AsteroidCandidateDecisionFact] = []
    seen_evidence: set[tuple[object, ...]] = set()

    for is_persisted, observations in ((True, persisted_items), (False, incoming_items)):
        for observation in observations:
            identity = observation_identity(observation)
            if identity in seen_evidence:
                if not is_persisted:
                    decisions.append(
                        AsteroidCandidateDecisionFact(
                            AsteroidCandidateDecision.SKIP_DUPLICATE,
                            observation,
                            None,
                            "Exact observation evidence is already stored or repeated",
                        )
                    )
                continue
            seen_evidence.add(identity)
            if not observation.structurally_valid:
                decisions.append(
                    AsteroidCandidateDecisionFact(
                        AsteroidCandidateDecision.SKIP_INVALID,
                        observation,
                        None,
                        "Observation is structurally invalid",
                    )
                )
                continue
            try:
                accepted.append(_candidate(observation, now=now, persisted=is_persisted))
            except ValueError as exc:
                decisions.append(
                    AsteroidCandidateDecisionFact(
                        AsteroidCandidateDecision.SKIP_OUT_OF_RANGE,
                        observation,
                        None,
                        str(exc),
                    )
                )

    groups: dict[str, list[AsteroidCandidate]] = {}
    for item in accepted:
        groups.setdefault(item.current_coord, []).append(item)

    selected: list[AsteroidCandidate] = []
    for current_coord in sorted(groups):
        group = sorted(groups[current_coord], key=_candidate_preference)
        winner = group[0]
        selected.append(winner)
        decisions.append(
            AsteroidCandidateDecisionFact(
                AsteroidCandidateDecision.KEEP if winner.persisted else AsteroidCandidateDecision.ADD,
                winner.observation,
                current_coord,
                "Selected freshest deterministic evidence for current coordinate",
            )
        )
        for duplicate in group[1:]:
            decisions.append(
                AsteroidCandidateDecisionFact(
                    AsteroidCandidateDecision.SKIP_DUPLICATE,
                    duplicate.observation,
                    current_coord,
                    "A fresher deterministic observation represents this current coordinate",
                )
            )

    selected.sort(key=_candidate_order)
    decisions.sort(
        key=lambda item: (
            item.current_coord or "999:999:999",
            item.decision.value,
            observation_identity(item.observation),
        )
    )
    return AsteroidCandidatePreview(tuple(selected), tuple(decisions))
