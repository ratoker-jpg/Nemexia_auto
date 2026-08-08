from pathlib import Path

import pytest

from v2.application.context import V2ApplicationContext
from v2.application.raid_actions import (
    RaidActionService, RaidCommand, RaidDispatchResult, RaidPreparation,
)
from v2.application.v2_queue import V2QueueRepository
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database


class FakeBackend:
    def __init__(self, *, verified: bool = True) -> None:
        self.calls = 0
        self.verified = verified

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        return RaidPreparation(command.home, command.target, command.player, command.ship_count, 60, 120, 5)

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        self.calls += 1
        return RaidDispatchResult(
            command.home, command.target, command.player, command.ship_count,
            "2026-08-08T10:00:00+00:00",
            "2026-08-08T10:01:00+00:00",
            "2026-08-08T10:02:00+00:00",
            "77" if self.verified else None,
            self.verified,
        )

    def close(self) -> None:
        pass


def build_context(tmp_path: Path, *, verified: bool = True):
    db = V2Database(tmp_path / "v2.sqlite3")
    db.import_raid_queue_rows([
        {
            "legacy_id": 1, "position": 1, "state": "queued", "coord": "3:1:2",
            "player": "Alpha", "metal": 10, "minerals": 20, "gas": 30,
            "last_spy_at": "2026-08-08T09:00:00+00:00", "enabled": True, "blacklisted": False,
        }
    ])
    queue = V2QueueRepository(db)
    settings = V2SettingsRepository(db)
    settings.set("actions_enabled", True)
    backend = FakeBackend(verified=verified)
    service = RaidActionService(backend, enabled=True)
    context = V2ApplicationContext(
        tmp_path / "missing-legacy.sqlite3",
        v2_database=db,
        v2_settings=settings,
        v2_queue=queue,
        raid_actions=service,
    )
    return context, backend


def test_verified_manual_dispatch_moves_queue_to_sent_and_journals(tmp_path: Path) -> None:
    context, backend = build_context(tmp_path, verified=True)
    try:
        item = context.plan()[0]
        result = context.dispatch_plan_raid(
            queue_id=item.id, target=item.coord, player=item.player,
            ship_count=25, request_id="manual-test-1",
        )
        assert result.verified is True
        assert backend.calls == 1
        assert context.plan()[0].state == "sent"
        record = context.recent_raid_actions(limit=1)[0]
        assert record.request_id == "manual-test-1"
        assert record.status == "verified"
    finally:
        context.close()


def test_unverified_manual_dispatch_marks_queue_ambiguous(tmp_path: Path) -> None:
    context, backend = build_context(tmp_path, verified=False)
    try:
        item = context.plan()[0]
        result = context.dispatch_plan_raid(
            queue_id=item.id, target=item.coord, player=item.player,
            ship_count=25, request_id="manual-test-2",
        )
        assert result.verified is False
        assert backend.calls == 1
        assert context.plan()[0].state == "ambiguous"
        assert context.recent_raid_actions(limit=1)[0].status == "ambiguous"
    finally:
        context.close()


def test_nonqueued_row_cannot_reach_dispatch_backend(tmp_path: Path) -> None:
    context, backend = build_context(tmp_path, verified=True)
    try:
        item = context.plan()[0]
        context.set_plan_state(item.id, "sent")
        with pytest.raises(RuntimeError, match="not queued"):
            context.dispatch_plan_raid(
                queue_id=item.id, target=item.coord, player=item.player,
                ship_count=25, request_id="manual-test-3",
            )
        assert backend.calls == 0
    finally:
        context.close()
