from pathlib import Path

import pytest

from v2.application.context import V2ApplicationContext
from v2.application.raid_actions import (
    RaidActionService,
    RaidActionsDisabled,
    RaidCommand,
    RaidDispatchResult,
    RaidPreparation,
)
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database


class PrepareBackend:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        self.calls.append(command)
        return RaidPreparation(
            source=command.home,
            target=command.target,
            player=command.player,
            ship_count=command.ship_count,
            one_way_seconds=60,
            round_trip_seconds=120,
        )

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        raise AssertionError("dispatch must not be used by V2-33")

    def close(self) -> None:
        self.closed = True


def test_context_action_gate_tracks_persisted_setting(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    settings = V2SettingsRepository(database)
    backend = PrepareBackend()
    service = RaidActionService(backend, enabled=bool(settings.get("actions_enabled")))
    context = V2ApplicationContext(
        tmp_path / "missing-legacy.sqlite3",
        v2_settings=settings,
        v2_database=database,
        raid_actions=service,
    )
    try:
        assert context.raid_actions_enabled() is False
        with pytest.raises(RaidActionsDisabled):
            context.prepare_raid("3:1:2", "Alpha", 25)
        assert backend.calls == []

        context.set_v2_setting("actions_enabled", True)
        assert context.raid_actions_enabled() is True
        prepared = context.prepare_raid("3:1:2", "Alpha", 25)
        assert prepared.source == "3:39:11"
        assert prepared.target == "3:1:2"
        assert backend.calls == [RaidCommand("3:1:2", "Alpha", 25, "3:39:11")]
    finally:
        context.close()
    assert backend.closed is True


def test_qt_bootstrap_constructs_guarded_action_backend() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app_qt.py").read_text(encoding="utf-8")
    assert "V2RaidCdpBackend" in source
    assert "RaidActionService" in source
    assert 'settings.get("actions_enabled")' in source
    assert "raid_actions=raid_actions" in source
