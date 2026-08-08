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
        self.before_dispatch = None

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        return RaidPreparation(command.home, command.target, command.player, command.ship_count, 60, 120, 5)

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        self.calls += 1
        if self.before_dispatch is not None:
            self.before_dispatch()
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


def build_context(
    tmp_path: Path,
    *,
    verified: bool = True,
    enabled: bool = True,
    blacklisted: bool = False,
):
    db = V2Database(tmp_path / "v2.sqlite3")
    db.import_raid_queue_rows([
        {
            "legacy_id": 1, "position": 1, "state": "queued", "coord": "3:1:2",
            "player": "Alpha", "metal": 10, "minerals": 20, "gas": 30,
            "last_spy_at": "2026-08-08T09:00:00+00:00",
            "enabled": enabled, "blacklisted": blacklisted,
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


def test_verified_manual_dispatch_locks_queue_before_backend_then_marks_sent(tmp_path: Path) -> None:
    context, backend = build_context(tmp_path, verified=True)
    try:
        item = context.plan()[0]
        backend.before_dispatch = lambda: (
            context.plan()[0].state == "sending"
            or (_ for _ in ()).throw(AssertionError("queue was retryable during SendFleet"))
        )
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


@pytest.mark.parametrize(
    ("enabled", "blacklisted", "message"),
    [
        (False, False, "disabled"),
        (True, True, "blacklisted"),
    ],
)
def test_disabled_or_blacklisted_queue_target_never_reaches_backend(
    tmp_path: Path, enabled: bool, blacklisted: bool, message: str,
) -> None:
    context, backend = build_context(
        tmp_path,
        enabled=enabled,
        blacklisted=blacklisted,
    )
    try:
        item = context.plan()[0]
        with pytest.raises(RuntimeError, match=message):
            context.dispatch_plan_raid(
                queue_id=item.id, target=item.coord, player=item.player,
                ship_count=25, request_id="manual-protected",
            )
        assert backend.calls == 0
        assert context.plan()[0].state == "queued"
        assert context.recent_raid_actions() == []
    finally:
        context.close()
