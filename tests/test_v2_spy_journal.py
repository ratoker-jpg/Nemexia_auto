from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from v2.application.spy_actions import (
    SpyActionError,
    SpyActionService,
    SpyActionsDisabled,
    SpyCaptchaBlocked,
    SpyRequestCommand,
    SpyRequestPreparation,
    SpyRequestRejected,
    SpyRequestResult,
)
from v2.application.spy_journal import SpyRequestBlocked, SpyRequestCoordinator
from v2.persistence.database import V2Database, V2DatabaseError


class JournalBackend:
    def __init__(
        self,
        *,
        mode: str = "verified",
        captcha: bool = False,
        available: int = 20,
        database: V2Database | None = None,
        observe_request_id: str | None = None,
    ) -> None:
        self.mode = mode
        self.captcha = captcha
        self.available = available
        self.database = database
        self.observe_request_id = observe_request_id
        self.prepares = 0
        self.requests = 0
        self.closed = False

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        self.prepares += 1
        return SpyRequestPreparation(
            source=command.source,
            target=command.target,
            probe_count=command.probe_count,
            probe_ship_key="spy_probe",
            available_probes=self.available,
            captcha_present=self.captcha,
            detail="CAPTCHA" if self.captcha else "ready",
        )

    def request(
        self,
        command: SpyRequestCommand,
        preparation: SpyRequestPreparation,
    ) -> SpyRequestResult:
        self.requests += 1
        if self.database is not None and self.observe_request_id is not None:
            row = self.database.read_spy_action(self.observe_request_id)
            assert row is not None
            assert row["status"] == "pending"
            assert row["source"] == command.source
            assert row["target"] == command.target
        if self.mode == "rejected":
            raise SpyRequestRejected("server proved request was not accepted")
        if self.mode == "error":
            raise RuntimeError("connection lost after request boundary")
        verified = self.mode == "verified"
        return SpyRequestResult(
            source=command.source,
            target=command.target,
            probe_count=command.probe_count,
            requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
            verified=verified,
            report_id="report-101" if verified else None,
            report_at=datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc) if verified else None,
            detail="verified fresh report" if verified else "request accepted but report not verified",
        )

    def close(self) -> None:
        self.closed = True


def _command(target: str = "3:1:2") -> SpyRequestCommand:
    return SpyRequestCommand("3:39:11", target, 5)


def test_disabled_invalid_and_captcha_fail_before_journal_or_request(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        disabled_backend = JournalBackend()
        disabled = SpyRequestCoordinator(SpyActionService(disabled_backend), db)
        with pytest.raises(SpyActionsDisabled):
            disabled.request(_command(), request_id="disabled")
        assert db.read_spy_action("disabled") is None
        assert disabled_backend.prepares == disabled_backend.requests == 0

        invalid_backend = JournalBackend()
        invalid = SpyRequestCoordinator(SpyActionService(invalid_backend, enabled=True), db)
        with pytest.raises(SpyActionError):
            invalid.request(SpyRequestCommand("bad", "3:1:2", 5), request_id="invalid")
        assert db.read_spy_action("invalid") is None
        assert invalid_backend.prepares == invalid_backend.requests == 0

        captcha_backend = JournalBackend(captcha=True)
        captcha = SpyRequestCoordinator(SpyActionService(captcha_backend, enabled=True), db)
        with pytest.raises(SpyCaptchaBlocked):
            captcha.request(_command(), request_id="captcha")
        assert db.read_spy_action("captcha") is None
        assert captcha_backend.prepares == 1
        assert captcha_backend.requests == 0


def test_pending_intent_exists_before_exactly_one_request_attempt(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(database=db, observe_request_id="req-1")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        result = coordinator.request(_command(), request_id="req-1")

        assert result.verified is True
        assert backend.prepares == 1
        assert backend.requests == 1
        record = coordinator.record("req-1")
        assert record is not None
        assert record.status == "verified"
        assert record.request_id == "req-1"
        assert record.source == "3:39:11"
        assert record.target == "3:1:2"
        assert record.probe_count == 5
        assert record.probe_ship_key == "spy_probe"
        assert record.available_probes == 20
        assert record.report_id == "report-101"
        assert record.requested_at == "2026-08-08T12:00:00+00:00"
        assert record.report_at == "2026-08-08T12:01:00+00:00"


def test_request_id_is_immutable_and_never_reused_even_after_verified(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend()
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        coordinator.request(_command(), request_id="immutable")
        with pytest.raises(SpyRequestBlocked, match="already exists"):
            coordinator.request(_command("3:1:3"), request_id="immutable")
        assert backend.requests == 1


def test_ambiguous_result_blocks_new_request_for_same_source_target(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="ambiguous")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        result = coordinator.request(_command(), request_id="amb-1")
        assert result.verified is False
        assert coordinator.record("amb-1").status == "ambiguous"

        with pytest.raises(SpyRequestBlocked, match="неоднозначная разведка"):
            coordinator.request(_command(), request_id="amb-2")
        assert backend.requests == 1
        assert db.read_spy_action("amb-2") is None


def test_exception_after_request_boundary_is_persisted_ambiguous(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="error")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        with pytest.raises(RuntimeError, match="connection lost"):
            coordinator.request(_command(), request_id="uncertain")
        record = coordinator.record("uncertain")
        assert record is not None
        assert record.status == "ambiguous"
        assert "connection lost" in record.detail
        assert backend.requests == 1


def test_unresolved_request_survives_restart_and_blocks_retry(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        db.begin_spy_action(
            request_id="crash-window",
            source="3:39:11",
            target="3:1:2",
            probe_count=5,
            probe_ship_key="spy_probe",
            available_probes=20,
        )

    with V2Database(path) as reopened:
        backend = JournalBackend()
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), reopened)
        with pytest.raises(SpyRequestBlocked, match="незавершённая"):
            coordinator.request(_command(), request_id="after-restart")
        assert backend.prepares == backend.requests == 0
        assert reopened.read_spy_action("crash-window")["status"] == "pending"


def test_proven_rejection_is_failed_safe_and_does_not_block_later_request(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        rejected_backend = JournalBackend(mode="rejected")
        rejected = SpyRequestCoordinator(SpyActionService(rejected_backend, enabled=True), db)
        with pytest.raises(SpyRequestRejected):
            rejected.request(_command(), request_id="safe-fail")
        assert rejected.record("safe-fail").status == "failed_safe"

        verified_backend = JournalBackend(mode="verified")
        verified = SpyRequestCoordinator(SpyActionService(verified_backend, enabled=True), db)
        assert verified.request(_command(), request_id="retry-after-safe-fail").verified is True
        assert verified_backend.requests == 1


def test_database_unique_index_closes_unresolved_target_race(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        db.begin_spy_action(
            request_id="race-a",
            source="3:39:11",
            target="3:1:2",
            probe_count=5,
            probe_ship_key="spy_probe",
            available_probes=20,
        )
        with pytest.raises(V2DatabaseError, match="unresolved target"):
            db.begin_spy_action(
                request_id="race-b",
                source="3:39:11",
                target="3:1:2",
                probe_count=5,
                probe_ship_key="spy_probe",
                available_probes=20,
            )


def test_ambiguous_request_can_only_be_resolved_with_exact_fresh_report_identity(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = JournalBackend(mode="ambiguous")
        coordinator = SpyRequestCoordinator(SpyActionService(backend, enabled=True), db)
        coordinator.request(_command(), request_id="resolve-me")

        with pytest.raises(SpyActionError, match="timezone-aware"):
            coordinator.resolve_verified(
                "resolve-me",
                report_id="report-202",
                report_at=datetime(2026, 8, 8, 12, 2),
            )

        resolved = coordinator.resolve_verified(
            "resolve-me",
            report_id="report-202",
            report_at=datetime(2026, 8, 8, 12, 2, tzinfo=timezone.utc),
        )
        assert resolved.status == "verified"
        assert resolved.report_id == "report-202"
        assert resolved.report_at == "2026-08-08T12:02:00+00:00"


def test_v2_44_has_no_real_spy_browser_dispatch(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "v2/application/spy_journal.py",
        "v2/persistence/database.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        for forbidden in (
            "processSpy",
            "ajax_fleets.php",
            "connect_over_cdp",
            ".click(",
            ".goto(",
            "page.evaluate",
            "BrowserWorker",
            "deleteSelectedMessages",
        ):
            assert forbidden not in source
