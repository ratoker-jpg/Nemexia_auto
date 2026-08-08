import pytest

from v2.application.raid_actions import (
    RaidActionError,
    RaidActionsDisabled,
    RaidActionService,
    RaidCommand,
    RaidDispatchResult,
    RaidPreparation,
)


class FakeBackend:
    def __init__(self) -> None:
        self.prepared = []
        self.dispatched = []
        self.closed = False

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        self.prepared.append(command)
        return RaidPreparation(
            source=command.home,
            target=command.target,
            player=command.player,
            ship_count=command.ship_count,
            one_way_seconds=60,
            round_trip_seconds=120,
            gas_needed=5,
        )

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        self.dispatched.append(command)
        return RaidDispatchResult(
            source=command.home,
            target=command.target,
            player=command.player,
            ship_count=command.ship_count,
            sent_at="2026-08-08T10:00:00+00:00",
            arrival_at="2026-08-08T10:01:00+00:00",
            return_at="2026-08-08T10:02:00+00:00",
            fleet_id="77",
            verified=True,
        )

    def close(self) -> None:
        self.closed = True


def test_actions_are_fail_closed_by_default() -> None:
    backend = FakeBackend()
    service = RaidActionService(backend)
    command = RaidCommand(" 3 : 1 : 2 ", "Alpha", 25, "3:39:11")
    with pytest.raises(RaidActionsDisabled):
        service.prepare(command)
    with pytest.raises(RaidActionsDisabled):
        service.dispatch(command)
    assert backend.prepared == []
    assert backend.dispatched == []


def test_enabled_service_normalizes_and_validates_before_backend() -> None:
    backend = FakeBackend()
    service = RaidActionService(backend, enabled=True)
    preparation = service.prepare(RaidCommand(" 3 : 1 : 2 ", "Alpha", 25, "3:39:11"))
    assert preparation.target == "3:1:2"
    assert backend.prepared[0] == RaidCommand("3:1:2", "Alpha", 25, "3:39:11")

    result = service.dispatch(RaidCommand("3:1:2", "Alpha", 25, "3:39:11"))
    assert result.verified is True
    assert result.fleet_id == "77"


@pytest.mark.parametrize(
    "command",
    [
        RaidCommand("bad", "Alpha", 25, "3:39:11"),
        RaidCommand("3:1:2", "Alpha", 0, "3:39:11"),
        RaidCommand("3:39:11", "Alpha", 25, "3:39:11"),
        RaidCommand("3:1:2", "Alpha", 25, "0:39:11"),
    ],
)
def test_invalid_commands_never_reach_backend(command: RaidCommand) -> None:
    backend = FakeBackend()
    service = RaidActionService(backend, enabled=True)
    with pytest.raises(RaidActionError):
        service.dispatch(command)
    assert backend.dispatched == []


def test_close_propagates_to_backend() -> None:
    backend = FakeBackend()
    service = RaidActionService(backend, enabled=True)
    service.close()
    assert backend.closed is True
