from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidActionsDisabled,
    AsteroidCaptchaBlocked,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchRejected,
    AsteroidDispatchResult,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds
from v2.persistence.asteroid_journal import AsteroidJournalRepository
from v2.persistence.database import V2Database, V2DatabaseError, V2_SCHEMA_VERSION


def observation() -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 6, 16, 45, 8, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 6, 17, 46, 8, tzinfo=timezone.utc),
        period_seconds=3660,
        observed_at=datetime(2026, 8, 6, 16, 57, 38, tzinfo=timezone.utc),
    )


def command(*, recycler_count: int = 5) -> AsteroidDispatchCommand:
    return AsteroidDispatchCommand(
        source="2:22:3",
        observation=observation(),
        recycler_count=recycler_count,
        safety_seconds=10,
    )


def preparation(*, recycler_count: int = 5, captcha: bool = False) -> AsteroidDispatchPreparation:
    obs = observation()
    prepared_at = datetime(2026, 8, 6, 17, 0, 0, tzinfo=timezone.utc)
    arrival_at = prepared_at + timedelta(seconds=300)
    return AsteroidDispatchPreparation(
        source="2:22:3",
        observation=obs,
        target="2:23:8",
        recycler_count=recycler_count,
        available_recyclers=20,
        free_fleet_slots=2,
        prepared_at=prepared_at,
        one_way_seconds=300,
        round_trip_seconds=600,
        shifts=0,
        arrival_at=arrival_at,
        return_at=prepared_at + timedelta(seconds=600),
        gas_needed=120,
        movement_margin_seconds=movement_margin_seconds(
            obs.next_move_at, obs.period_seconds, arrival_at
        ),
        captcha_present=captcha,
        detail="captcha" if captcha else "ready",
    )


def result(*, recycler_count: int = 5) -> AsteroidDispatchResult:
    sent_at = datetime(2026, 8, 6, 17, 0, 2, tzinfo=timezone.utc)
    return AsteroidDispatchResult(
        source="2:22:3",
        observation_coord="2:23:8",
        target="2:23:8",
        recycler_count=recycler_count,
        sent_at=sent_at,
        arrival_at=sent_at + timedelta(seconds=300),
        return_at=sent_at + timedelta(seconds=600),
        fleet_id="99123",
        verified=True,
        server_info="verified",
    )


class JournalBackend:
    def __init__(
        self,
        *,
        database: V2Database | None = None,
        request_id: str | None = None,
        prepared: AsteroidDispatchPreparation | None = None,
        mode: str = "verified",
    ) -> None:
        self.database = database
        self.request_id = request_id
        self.prepared = prepared or preparation()
        self.mode = mode
        self.prepare_calls = 0
        self.dispatch_calls = 0
        self.saw_pending = False

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        self.prepare_calls += 1
        return self.prepared

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        prepared: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        self.dispatch_calls += 1
        if self.database is not None and self.request_id:
            row = AsteroidJournalRepository(self.database).read(self.request_id)
            self.saw_pending = bool(row and row["status"] == "pending")
        if self.mode == "ambiguous":
            raise RuntimeError("connection lost after possible SendFleet")
        if self.mode == "rejected":
            raise AsteroidDispatchRejected("server pass=0")
        return result(recycler_count=command.recycler_count)

    def close(self) -> None:
        return None


def test_schema_v7_contains_asteroid_journal_and_unresolved_unique_index(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        assert db.schema_version() == V2_SCHEMA_VERSION == 7
        assert "asteroid_actions" in db.table_names()
        indexes = {
            str(row[1])
            for row in db._require_conn().execute("PRAGMA index_list(asteroid_actions)").fetchall()
        }
        assert "idx_asteroid_actions_unresolved_identity" in indexes


def test_pending_is_committed_before_backend_side_effect_and_verified_after(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(database=db, request_id="asteroid-1")
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        dispatched = coordinator.dispatch(command(), request_id="asteroid-1")
        assert dispatched.verified
        assert backend.dispatch_calls == 1
        assert backend.saw_pending
        record = coordinator.record("asteroid-1")
        assert record is not None
        assert record.status == "verified"
        assert record.fleet_id == "99123"


def test_unclassified_failure_after_pending_becomes_ambiguous_and_blocks_retry(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        backend = JournalBackend(database=db, request_id="asteroid-amb", mode="ambiguous")
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        with pytest.raises(RuntimeError, match="possible SendFleet"):
            coordinator.dispatch(command(), request_id="asteroid-amb")
        assert backend.saw_pending and backend.dispatch_calls == 1
        record = coordinator.record("asteroid-amb")
        assert record is not None and record.status == "ambiguous"

    # Restart: changing recycler_count must not bypass the unresolved trajectory identity.
    with V2Database(path) as reopened:
        second_backend = JournalBackend(prepared=preparation(recycler_count=6))
        second = AsteroidRequestCoordinator(AsteroidActionService(second_backend, enabled=True), reopened)
        with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
            second.dispatch(command(recycler_count=6), request_id="asteroid-new-id")
        assert second_backend.dispatch_calls == 0


def test_database_unique_index_closes_race_between_two_coordinators(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = AsteroidJournalRepository(db)
        prepared = preparation()
        obs = prepared.observation
        common = dict(
            source=prepared.source,
            observation_coord=obs.coord,
            observation_last_move_at=obs.last_move_at.isoformat(),
            observation_next_move_at=obs.next_move_at.isoformat(),
            observation_period_seconds=obs.period_seconds,
            observation_observed_at=obs.observed_at.isoformat(),
            target=prepared.target,
            recycler_count=5,
            safety_seconds=10,
            prepared_at=prepared.prepared_at.isoformat(),
            one_way_seconds=prepared.one_way_seconds,
            round_trip_seconds=prepared.round_trip_seconds,
            shifts=prepared.shifts,
            gas_needed=prepared.gas_needed,
        )
        repo.begin(request_id="race-a", **common)
        with pytest.raises(V2DatabaseError, match="unresolved trajectory"):
            repo.begin(request_id="race-b", **{**common, "recycler_count": 7})


def test_explicit_proven_rejection_becomes_failed_safe_not_ambiguous(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="rejected")
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        with pytest.raises(AsteroidDispatchRejected, match="pass=0"):
            coordinator.dispatch(command(), request_id="asteroid-rejected")
        record = coordinator.record("asteroid-rejected")
        assert record is not None and record.status == "failed_safe"
        assert backend.dispatch_calls == 1


def test_gate_and_captcha_fail_before_remote_dispatch(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        disabled_backend = JournalBackend()
        disabled = AsteroidRequestCoordinator(AsteroidActionService(disabled_backend), db)
        with pytest.raises(AsteroidActionsDisabled):
            disabled.dispatch(command(), request_id="disabled")
        assert disabled_backend.prepare_calls == disabled_backend.dispatch_calls == 0
        assert disabled.record("disabled") is None

        captcha_backend = JournalBackend(prepared=preparation(captcha=True))
        captcha = AsteroidRequestCoordinator(AsteroidActionService(captcha_backend, enabled=True), db)
        with pytest.raises(AsteroidCaptchaBlocked):
            captcha.dispatch(command(), request_id="captcha")
        assert captcha_backend.dispatch_calls == 0
        assert captcha.record("captcha") is None


def test_request_id_is_immutable_and_resolved_rows_allow_later_new_dispatch(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        first = AsteroidRequestCoordinator(AsteroidActionService(JournalBackend(), enabled=True), db)
        first.dispatch(command(), request_id="immutable")
        with pytest.raises(AsteroidRequestBlocked, match="already exists"):
            first.dispatch(command(), request_id="immutable")

        # Verified rows are resolved, so a new immutable request may intentionally
        # dispatch the same trajectory again; unresolved rows alone block retries.
        second_backend = JournalBackend()
        second = AsteroidRequestCoordinator(AsteroidActionService(second_backend, enabled=True), db)
        second.dispatch(command(), request_id="intentional-second")
        assert second_backend.dispatch_calls == 1


def test_manual_reconciliation_can_only_resolve_pending_or_ambiguous(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="ambiguous")
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        with pytest.raises(RuntimeError):
            coordinator.dispatch(command(), request_id="reconcile")
        resolved = coordinator.resolve_verified(
            "reconcile",
            fleet_id="99124",
            sent_at=datetime(2026, 8, 6, 17, 0, 2, tzinfo=timezone.utc),
        )
        assert resolved.status == "verified"
        assert resolved.fleet_id == "99124"
