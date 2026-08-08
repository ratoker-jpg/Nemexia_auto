from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from v2.application.debris_repository import V2DebrisRepository
from v2.application.debris_source import DebrisReadSnapshot
from v2.domain.asteroids import AsteroidObservationFact
from v2.domain.debris import DebrisObservationFact, DebrisReadState
from v2.domain.debris_candidates import DebrisCandidateDecision
from v2.persistence.database import V2Database


UTC = timezone.utc
BASE = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def fact(*, galaxy: int = 1, system: int = 39, position: int = 24, observed_at=BASE) -> DebrisObservationFact:
    asteroid = AsteroidObservationFact(
        galaxy=galaxy,
        system=system,
        position=position,
        last_move_at=BASE - timedelta(minutes=60),
        next_move_at=BASE + timedelta(minutes=60),
        period_seconds=3600,
        observed_at=observed_at,
    )
    return DebrisObservationFact(asteroid=asteroid)


def test_debris_evidence_is_immutable_idempotent_and_survives_restart(tmp_path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        repo = V2DebrisRepository(db)
        result = repo.ingest([fact()], now=BASE)
        assert result.inserted == 1
        assert result.exact_duplicates == 0
        duplicate = repo.ingest([fact()], now=BASE)
        assert duplicate.inserted == 0
        assert duplicate.exact_duplicates == 1
        assert "debris_observations" in db.table_names()

    with V2Database(path) as db:
        repo = V2DebrisRepository(db)
        restored = repo.observations()
        assert len(restored) == 1
        assert restored[0].coord == "1:39:24"
        assert restored[0].marker == "Этот астероид содержит обломки"


def test_current_system_no_debris_never_erases_other_system_evidence(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2DebrisRepository(db)
        repo.ingest([fact(galaxy=2, system=20, position=7)], now=BASE)
        empty = DebrisReadSnapshot(
            DebrisReadState.NO_DEBRIS,
            (),
            visible_asteroids=2,
            readable_square_info=2,
            detail="No debris in currently opened system 1:40",
        )
        result = repo.ingest_read(empty, now=BASE)
        assert result.inserted == 0
        assert [item.coord for item in repo.observations()] == ["2:20:7"]


def test_partial_unavailable_and_captcha_reads_cannot_be_ingested(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2DebrisRepository(db)
        for state in (
            DebrisReadState.PARTIAL_EVIDENCE,
            DebrisReadState.LIVE_UNAVAILABLE,
            DebrisReadState.CAPTCHA,
        ):
            snapshot = DebrisReadSnapshot(state, (fact(),), 1, 0, state.value)
            with pytest.raises(ValueError, match="incomplete debris read"):
                repo.ingest_read(snapshot, now=BASE)
        assert repo.observations() == ()


def test_projection_uses_existing_asteroid_movement_model(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2DebrisRepository(db)
        observation = fact(system=39, position=24)
        result = repo.ingest([observation], now=BASE + timedelta(hours=1, seconds=1))
        assert result.inserted == 1
        assert len(result.preview.candidates) == 1
        candidate = result.preview.candidates[0]
        assert candidate.current_coord == "1:40:1"
        assert candidate.shifts == 1
        assert any(item.decision is DebrisCandidateDecision.ADD for item in result.preview.decisions)


def test_out_of_range_projection_is_rejected_and_not_persisted(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2DebrisRepository(db)
        result = repo.ingest(
            [fact(system=40, position=24)],
            now=BASE + timedelta(hours=1, seconds=1),
        )
        assert result.inserted == 0
        assert repo.observations() == ()
        assert any(
            item.decision is DebrisCandidateDecision.SKIP_OUT_OF_RANGE
            for item in result.preview.decisions
        )


def test_reading_two_manually_opened_systems_accumulates_evidence(tmp_path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2DebrisRepository(db)
        first = DebrisReadSnapshot(DebrisReadState.READY, (fact(system=40, position=2),), 1, 1)
        second = DebrisReadSnapshot(DebrisReadState.READY, (fact(system=12, position=4),), 1, 1)
        repo.ingest_read(first, now=BASE)
        repo.ingest_read(second, now=BASE)
        assert {item.coord for item in repo.observations()} == {"1:40:2", "1:12:4"}
