from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2.application.asteroid_repository import V2AsteroidRepository
from v2.domain.asteroid_candidates import AsteroidCandidateDecision
from v2.domain.asteroids import AsteroidObservationFact
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION


def fact(
    *,
    system: int = 23,
    position: int = 8,
    observed_at: datetime | None = None,
    next_move_at: datetime | None = None,
) -> AsteroidObservationFact:
    observed_at = observed_at or datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    next_move_at = next_move_at or datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc)
    return AsteroidObservationFact(
        galaxy=2,
        system=system,
        position=position,
        last_move_at=next_move_at - timedelta(hours=1),
        next_move_at=next_move_at,
        period_seconds=3600,
        observed_at=observed_at,
        source="galaxy.squareInfo",
    )


def test_schema_v8_and_restart_preserve_immutable_observations(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    now = datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc)
    item = fact()
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION == 8
        assert "asteroid_observations" in db.table_names()
        result = V2AsteroidRepository(db).ingest((item,), now=now)
        assert result.inserted == 1
        assert [candidate.current_coord for candidate in result.preview.candidates] == ["2:23:8"]

    with V2Database(path) as reopened:
        repository = V2AsteroidRepository(reopened)
        assert repository.observations() == (item,)
        assert [candidate.current_coord for candidate in repository.preview(now=now).candidates] == ["2:23:8"]


def test_timezone_equivalent_evidence_is_one_persistent_identity(tmp_path: Path) -> None:
    base = fact()
    offset = timezone(timedelta(hours=2))
    same = replace(
        base,
        last_move_at=base.last_move_at.astimezone(offset),
        next_move_at=base.next_move_at.astimezone(offset),
        observed_at=base.observed_at.astimezone(offset),
    )
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repository = V2AsteroidRepository(db)
        first = repository.ingest((base,), now=datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc))
        second = repository.ingest((same,), now=datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc))
        assert first.inserted == 1
        assert second.inserted == 0
        assert second.exact_duplicates == 1
        assert len(repository.observations()) == 1


def test_candidate_collision_keeps_provenance_but_selects_freshest_view(tmp_path: Path) -> None:
    older = fact(
        system=23,
        position=8,
        observed_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
    )
    newer = fact(
        system=23,
        position=10,
        observed_at=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )
    now = datetime(2026, 8, 8, 12, 30, tzinfo=timezone.utc)
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repository = V2AsteroidRepository(db)
        result = repository.ingest((older, newer), now=now)
        assert result.inserted == 2
        assert len(repository.observations()) == 2
        assert len(result.preview.candidates) == 1
        assert result.preview.candidates[0].observation == newer
        assert any(
            decision.decision is AsteroidCandidateDecision.SKIP_DUPLICATE
            and decision.observation == older
            for decision in result.preview.decisions
        )


def test_out_of_range_evidence_is_rejected_from_owned_candidate_state(tmp_path: Path) -> None:
    leaving = fact(
        system=40,
        position=24,
        next_move_at=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc),
    )
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repository = V2AsteroidRepository(db)
        result = repository.ingest(
            (leaving,),
            now=datetime(2026, 8, 8, 11, 1, tzinfo=timezone.utc),
        )
        assert result.inserted == 0
        assert repository.observations() == ()
        assert any(
            decision.decision is AsteroidCandidateDecision.SKIP_OUT_OF_RANGE
            for decision in result.preview.decisions
        )


def test_projection_does_not_drop_older_valid_evidence_after_5000_rows(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    now = datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc)
    older_distinct = fact(
        system=22,
        position=1,
        observed_at=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
    )
    newer_same_candidate = tuple(
        fact(
            system=23,
            position=8,
            observed_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)
            + timedelta(microseconds=index),
        )
        for index in range(5000)
    )
    with V2Database(path) as db:
        repository = V2AsteroidRepository(db)
        assert repository.ingest((older_distinct,), now=now).inserted == 1
        assert repository.ingest(newer_same_candidate, now=now).inserted == 5000
        assert len(repository.observations()) == 5001

    with V2Database(path) as reopened:
        preview = V2AsteroidRepository(reopened).preview(now=now)
        assert [candidate.current_coord for candidate in preview.candidates] == ["2:23:8", "2:22:1"]


def test_no_browser_or_side_effect_dependency_in_candidate_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    combined = (
        (root / "v2/application/asteroid_repository.py").read_text(encoding="utf-8")
        + (root / "v2/domain/asteroid_candidates.py").read_text(encoding="utf-8")
    )
    for forbidden in (
        "playwright", "SendFleet", "ajax_", ".goto(", "page.evaluate",
        "processSpy", "deleteSelectedMessages", "QTimer",
    ):
        assert forbidden not in combined
