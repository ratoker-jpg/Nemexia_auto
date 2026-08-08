from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from v2.application.spy_actions import (
    SpyActionError, SpyActionService, SpyActionsDisabled, SpyCaptchaBlocked,
    SpyRequestCommand, SpyRequestPreparation, SpyRequestRejected, SpyRequestResult,
)
from v2.application.spy_journal import SpyRequestBlocked, SpyRequestCoordinator
from v2.persistence.database import V2Database, V2DatabaseError


class JournalBackend:
    def __init__(self, *, mode="verified", captcha=False, database=None, observe_request_id=None, target="3:1:2"):
        self.mode = mode; self.captcha = captcha; self.database = database
        self.observe_request_id = observe_request_id; self.target = target
        self.prepares = 0; self.requests = 0

    def prepare(self, command):
        self.prepares += 1
        return SpyRequestPreparation(
            fleet_id=command.fleet_id, source="3:39:11", target=self.target,
            captcha_present=self.captcha, detail="CAPTCHA" if self.captcha else "ready",
        )

    def request(self, command, preparation):
        self.requests += 1
        if self.database is not None and self.observe_request_id:
            row = self.database.read_spy_action(self.observe_request_id)
            assert row and row["status"] == "pending" and row["fleet_id"] == command.fleet_id
        if self.mode == "rejected":
            raise SpyRequestRejected("proved no side effect")
        if self.mode == "error":
            raise RuntimeError("connection lost after request boundary")
        verified = self.mode == "verified"
        return SpyRequestResult(
            fleet_id=command.fleet_id, source=preparation.source, target=preparation.target,
            requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc), verified=verified,
            report_id="report-101" if verified else None,
            report_at=datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc) if verified else None,
            detail="verified" if verified else "not verified",
        )

    def close(self): pass


def _command(fleet_id="152272"):
    return SpyRequestCommand(fleet_id)


def test_precondition_failures_happen_before_journal_and_side_effect(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        disabled_backend = JournalBackend()
        with pytest.raises(SpyActionsDisabled):
            SpyRequestCoordinator(SpyActionService(disabled_backend), db).request(_command(), request_id="disabled")
        assert db.read_spy_action("disabled") is None and disabled_backend.requests == 0

        invalid_backend = JournalBackend()
        with pytest.raises(SpyActionError):
            SpyRequestCoordinator(SpyActionService(invalid_backend, enabled=True), db).request(
                _command("bad"), request_id="invalid"
            )
        assert db.read_spy_action("invalid") is None and invalid_backend.requests == 0

        captcha_backend = JournalBackend(captcha=True)
        with pytest.raises(SpyCaptchaBlocked):
            SpyRequestCoordinator(SpyActionService(captcha_backend, enabled=True), db).request(
                _command(), request_id="captcha"
            )
        assert db.read_spy_action("captcha") is None and captcha_backend.requests == 0


def test_pending_exact_fleet_intent_exists_before_one_request_attempt(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(database=db, observe_request_id="req-1")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        result = coordinator.request(_command(), request_id="req-1")
        assert result.verified and backend.prepares == 1 and backend.requests == 1
        record = coordinator.record("req-1")
        assert record and record.status == "verified" and record.fleet_id == "152272"
        assert (record.source, record.target, record.report_id) == ("3:39:11", "3:1:2", "report-101")


def test_request_id_and_unresolved_fleet_are_idempotent(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="ambiguous")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        coordinator.request(_command(), request_id="amb-1")
        assert coordinator.record("amb-1").status == "ambiguous"
        with pytest.raises(SpyRequestBlocked):
            coordinator.request(_command(), request_id="amb-2")
        with pytest.raises(SpyRequestBlocked, match="already exists"):
            coordinator.request(_command("152273"), request_id="amb-1")
        assert backend.requests == 1


def test_unresolved_target_blocks_different_fleet_for_same_route(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        first = JournalBackend(mode="ambiguous", target="3:1:2")
        SpyRequestCoordinator(SpyActionService(first, enabled=True), db).request(_command("152272"), request_id="a")
        second = JournalBackend(target="3:1:2")
        with pytest.raises(SpyRequestBlocked, match="разведка на эту цель"):
            SpyRequestCoordinator(SpyActionService(second, enabled=True), db).request(_command("152273"), request_id="b")
        assert second.requests == 0


def test_exception_after_boundary_is_ambiguous_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        backend = JournalBackend(mode="error")
        with pytest.raises(RuntimeError):
            SpyRequestCoordinator(SpyActionService(backend, enabled=True), db).request(_command(), request_id="uncertain")
        assert db.read_spy_action("uncertain")["status"] == "ambiguous"
    with V2Database(path) as reopened:
        backend = JournalBackend()
        with pytest.raises(SpyRequestBlocked):
            SpyRequestCoordinator(SpyActionService(backend, enabled=True), reopened).request(_command(), request_id="retry")
        assert backend.requests == 0


def test_proven_rejection_is_failed_safe(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = SpyRequestCoordinator(SpyActionService(JournalBackend(mode="rejected"), enabled=True), db)
        with pytest.raises(SpyRequestRejected):
            coordinator.request(_command(), request_id="safe")
        assert coordinator.record("safe").status == "failed_safe"


def test_database_unique_index_closes_fleet_race(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        db.begin_spy_action(request_id="a", fleet_id="152272", source="3:39:11", target="3:1:2")
        with pytest.raises(V2DatabaseError):
            db.begin_spy_action(request_id="b", fleet_id="152272", source="3:39:11", target="3:1:3")


def test_ambiguous_can_be_reconciled_only_with_aware_report_time(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = SpyRequestCoordinator(SpyActionService(JournalBackend(mode="ambiguous"), enabled=True), db)
        coordinator.request(_command(), request_id="resolve")
        with pytest.raises(SpyActionError, match="timezone-aware"):
            coordinator.resolve_verified("resolve", report_id="r2", report_at=datetime(2026, 8, 8, 12, 2))
        record = coordinator.resolve_verified(
            "resolve", report_id="r2", report_at=datetime(2026, 8, 8, 12, 2, tzinfo=timezone.utc)
        )
        assert record.status == "verified" and record.report_id == "r2"
