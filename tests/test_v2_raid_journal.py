from pathlib import Path

import pytest

from v2.application.raid_actions import (
    RaidActionError,
    RaidActionService,
    RaidCommand,
    RaidDispatchResult,
    RaidPreparation,
)
from v2.application.raid_journal import RaidDispatchCoordinator, RaidRequestBlocked
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION


class FakeBackend:
    def __init__(self, *, verified: bool = True, fail: bool = False) -> None:
        self.calls = 0
        self.verified = verified
        self.fail = fail

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        return RaidPreparation(command.home, command.target, command.player, command.ship_count, 60, 120)

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        self.calls += 1
        if self.fail:
            raise RaidActionError("network state unknown")
        return RaidDispatchResult(
            source=command.home,
            target=command.target,
            player=command.player,
            ship_count=command.ship_count,
            sent_at="2026-08-08T10:00:00+00:00",
            arrival_at="2026-08-08T10:01:00+00:00",
            return_at="2026-08-08T10:02:00+00:00",
            fleet_id="77" if self.verified else None,
            verified=self.verified,
        )

    def close(self) -> None:
        return None


def command(target: str = "3:1:2") -> RaidCommand:
    return RaidCommand(target, "Alpha", 25, "3:39:11")


def test_verified_dispatch_is_journaled_before_duplicate_is_blocked(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = FakeBackend(verified=True)
        coordinator = RaidDispatchCoordinator(RaidActionService(backend, enabled=True), db)
        result = coordinator.dispatch(command(), request_id="manual-1")
        assert result.verified is True
        record = coordinator.record("manual-1")
        assert record is not None
        assert record.status == "verified"
        assert record.fleet_id == "77"
        with pytest.raises(RaidRequestBlocked):
            coordinator.dispatch(command(), request_id="manual-1")
        assert backend.calls == 1


def test_unverified_result_blocks_new_request_for_same_target(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = FakeBackend(verified=False)
        coordinator = RaidDispatchCoordinator(RaidActionService(backend, enabled=True), db)
        result = coordinator.dispatch(command(), request_id="manual-2")
        assert result.verified is False
        assert coordinator.record("manual-2").status == "ambiguous"
        with pytest.raises(RaidRequestBlocked):
            coordinator.dispatch(command(), request_id="manual-3")
        assert backend.calls == 1


def test_exception_after_journal_is_conservatively_ambiguous(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = FakeBackend(fail=True)
        coordinator = RaidDispatchCoordinator(RaidActionService(backend, enabled=True), db)
        with pytest.raises(RaidActionError, match="network state unknown"):
            coordinator.dispatch(command(), request_id="manual-4")
        record = coordinator.record("manual-4")
        assert record is not None
        assert record.status == "ambiguous"
        with pytest.raises(RaidRequestBlocked):
            coordinator.dispatch(command(), request_id="manual-5")
        assert backend.calls == 1


def test_disabled_actions_do_not_create_journal_row(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        backend = FakeBackend()
        coordinator = RaidDispatchCoordinator(RaidActionService(backend, enabled=False), db)
        with pytest.raises(RaidActionError):
            coordinator.dispatch(command(), request_id="disabled-1")
        assert db.read_raid_action("disabled-1") is None
        assert backend.calls == 0


def test_raid_journal_survives_later_schema_migrations(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION
        assert "raid_actions" in db.table_names()
        db.write_setting_raw("cdp_port", "9333")
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION
        assert db.read_setting_raw("cdp_port") == "9333"
        assert db.integrity_check() == "ok"
