from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from v2.domain.asteroid_candidates import (
    AsteroidCandidateDecision,
    build_candidate_preview,
    observation_identity,
)
from v2.domain.asteroids import AsteroidObservationFact


def fact(
    *,
    galaxy: int = 2,
    system: int = 23,
    position: int = 8,
    observed_at: datetime | None = None,
    next_move_at: datetime | None = None,
    period_seconds: int = 3600,
    source: str = "galaxy.squareInfo",
) -> AsteroidObservationFact:
    observed_at = observed_at or datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    next_move_at = next_move_at or datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc)
    return AsteroidObservationFact(
        galaxy=galaxy,
        system=system,
        position=position,
        last_move_at=next_move_at - timedelta(seconds=period_seconds),
        next_move_at=next_move_at,
        period_seconds=period_seconds,
        observed_at=observed_at,
        source=source,
    )


def test_timezone_spelling_does_not_change_observation_identity() -> None:
    base = fact()
    offset = timezone(timedelta(hours=2))
    same = replace(
        base,
        last_move_at=base.last_move_at.astimezone(offset),
        next_move_at=base.next_move_at.astimezone(offset),
        observed_at=base.observed_at.astimezone(offset),
    )
    assert observation_identity(base) == observation_identity(same)


def test_same_input_and_now_produce_same_candidate_order_and_diff() -> None:
    now = datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc)
    persisted = (fact(system=25, position=2), fact(system=24, position=9))
    incoming = (fact(system=25, position=3), fact(system=23, position=4))
    first = build_candidate_preview(persisted=persisted, incoming=incoming, now=now)
    second = build_candidate_preview(persisted=persisted, incoming=incoming, now=now)
    assert first == second
    assert [item.current_coord for item in first.candidates] == ["2:25:2", "2:25:3", "2:24:9", "2:23:4"]


def test_freshest_evidence_wins_when_two_observations_predict_same_current_coord() -> None:
    now = datetime(2026, 8, 8, 12, 30, tzinfo=timezone.utc)
    older = fact(
        system=23,
        position=8,
        observed_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
    )
    # Same moving asteroid observed two shifts later at 23:10 with the same phase.
    newer = fact(
        system=23,
        position=10,
        observed_at=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )
    preview = build_candidate_preview(persisted=(older,), incoming=(newer,), now=now)
    assert len(preview.candidates) == 1
    assert preview.candidates[0].observation == newer
    assert preview.candidates[0].current_coord == "2:23:11"
    decisions = {item.observation: item.decision for item in preview.decisions}
    assert decisions[newer] is AsteroidCandidateDecision.ADD
    assert decisions[older] is AsteroidCandidateDecision.SKIP_DUPLICATE


def test_exact_persisted_evidence_is_kept_and_incoming_duplicate_is_skipped() -> None:
    item = fact()
    preview = build_candidate_preview(
        persisted=(item,),
        incoming=(item,),
        now=datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc),
    )
    assert len(preview.candidates) == 1 and preview.candidates[0].persisted
    assert preview.kept == 1
    assert any(
        decision.decision is AsteroidCandidateDecision.SKIP_DUPLICATE
        for decision in preview.decisions
    )


def test_candidate_falls_out_of_range_after_system_40_without_age_ttl() -> None:
    item = fact(
        system=40,
        position=24,
        observed_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc),
    )
    # Very old observed_at is not itself a rejection: before next movement it is valid.
    before = build_candidate_preview(
        persisted=(item,),
        incoming=(),
        now=datetime(2026, 8, 8, 10, 59, tzinfo=timezone.utc),
    )
    assert [candidate.current_coord for candidate in before.candidates] == ["2:40:24"]

    after = build_candidate_preview(
        persisted=(item,),
        incoming=(),
        now=datetime(2026, 8, 8, 11, 1, tzinfo=timezone.utc),
    )
    assert after.candidates == ()
    assert any(
        decision.decision is AsteroidCandidateDecision.SKIP_OUT_OF_RANGE
        for decision in after.decisions
    )
