from dataclasses import replace

import pytest

from v2.application.farm_controller import FarmController, FarmState
from v2.application.flight_source import FleetCapacitySnapshot, FlightSourceStatus
from v2.application.live_overview import LiveOverviewSnapshot
from v2.application.raid_actions import RaidDispatchResult
from v2.application.raid_journal import RaidActionRecord
from v2.application.read_store import QueueSnapshot


def queue_item(item_id: int, coord: str, *, enabled: bool = True, blacklisted: bool = False):
    return QueueSnapshot(
        id=item_id,
        position=item_id,
        state="queued",
        coord=coord,
        player=f"P{item_id}",
        metal=0,
        minerals=0,
        gas=0,
        last_spy_at="2026-08-08T10:00:00+00:00",
        enabled=enabled,
        blacklisted=blacklisted,
    )


class Runtime:
    def __init__(self) -> None:
        self.actions = True
        self.status = FlightSourceStatus(True, "ok")
        self.capacity = FleetCapacitySnapshot(used=20, maximum=22, free=2, source="fixture")
        self.blocking = []
        self.queue = [queue_item(1, "3:1:2"), queue_item(2, "3:1:3"), queue_item(3, "3:1:4")]
        self.journal = []
        self.calls = []
        self.unverified_target = None
        self.live_ready_at = None
        self.return_buffer = 5

    def raid_actions_enabled(self): return self.actions
    def cached_flight_status(self): return self.status
    def fleet_capacity(self): return self.capacity
    def farm_blocking_flights(self): return self.blocking
    def plan(self, *, limit=5000): return self.queue[:limit]
    def recent_raid_actions(self, *, limit=200): return self.journal[:limit]
    def v2_setting(self, key, default=None):
        return self.return_buffer if key == "farm_return_buffer_minutes" else default
    def live_overview_snapshot(self):
        return LiveOverviewSnapshot(
            checked=True,
            available=True,
            detail="ok",
            capacity=self.capacity,
            farm_blocking_count=len(self.blocking),
            inferred_farm_ready_at=self.live_ready_at,
        )

    def dispatch_plan_raid(self, *, queue_id, target, player, ship_count, request_id):
        self.calls.append((queue_id, target, ship_count, request_id))
        verified = target != self.unverified_target
        return RaidDispatchResult(
            source="3:39:11", target=target, player=player, ship_count=ship_count,
            sent_at="2026-08-08T10:00:00+00:00",
            arrival_at="2026-08-08T10:01:00+00:00",
            return_at="2026-08-08T10:02:00+00:00",
            fleet_id="77" if verified else None,
            verified=verified,
        )


def action_record(
    *,
    request_id="r1",
    status="ambiguous",
    return_at=None,
):
    return RaidActionRecord(
        request_id=request_id, source="3:39:11", target="3:1:9", player="X", ship_count=25,
        status=status, fleet_id="77" if status == "verified" else None,
        sent_at="2026-08-08T10:00:00+00:00" if status == "verified" else None,
        arrival_at=None, return_at=return_at,
        created_at="2026-08-08T10:00:00+00:00", detail="unknown",
    )


def test_snapshot_gates_in_safety_order() -> None:
    controller = FarmController()
    runtime = Runtime()

    runtime.actions = False
    assert controller.snapshot(runtime).state is FarmState.ACTIONS_DISABLED
    runtime.actions = True

    runtime.status = None
    assert controller.snapshot(runtime).state is FarmState.LIVE_NOT_CHECKED
    runtime.status = FlightSourceStatus(False, "offline")
    assert controller.snapshot(runtime).state is FarmState.LIVE_UNAVAILABLE
    runtime.status = FlightSourceStatus(True, "ok")

    runtime.journal = [action_record()]
    assert controller.snapshot(runtime).state is FarmState.BLOCKED_UNRESOLVED
    runtime.journal = []

    runtime.blocking = [object()]
    runtime.live_ready_at = "2099-08-08T10:15:00+00:00"
    waiting = controller.snapshot(runtime)
    assert waiting.state is FarmState.WAITING_RETURN
    assert waiting.ready_at == "2099-08-08T10:15:00+00:00"
    runtime.blocking = []
    runtime.live_ready_at = None

    runtime.capacity = FleetCapacitySnapshot(used=22, maximum=22, free=0, source="fixture")
    assert controller.snapshot(runtime).state is FarmState.WAITING_CAPACITY
    runtime.capacity = FleetCapacitySnapshot(used=20, maximum=22, free=2, source="fixture")

    runtime.queue = [replace(queue_item(1, "3:1:2"), enabled=False), queue_item(2, "3:1:3", blacklisted=True)]
    assert controller.snapshot(runtime).state is FarmState.NO_TARGETS


def test_verified_farm_journal_preserves_return_buffer_across_restart() -> None:
    runtime = Runtime()
    runtime.return_buffer = 7
    runtime.journal = [
        action_record(
            request_id="farm-persisted-wave",
            status="verified",
            return_at="2099-08-08T10:00:00+00:00",
        )
    ]
    snapshot = FarmController().snapshot(runtime)
    assert snapshot.state is FarmState.WAITING_RETURN
    assert snapshot.ready_at == "2099-08-08T10:07:00+00:00"
    assert "return-buffer" in snapshot.detail


def test_manual_verified_action_does_not_create_persisted_farm_buffer() -> None:
    runtime = Runtime()
    runtime.journal = [
        action_record(
            request_id="manual-raid",
            status="verified",
            return_at="2099-08-08T10:00:00+00:00",
        )
    ]
    assert FarmController().snapshot(runtime).state is FarmState.READY


def test_ready_snapshot_counts_only_eligible_queue() -> None:
    runtime = Runtime()
    runtime.queue.append(queue_item(4, "3:1:5", enabled=False))
    runtime.queue.append(queue_item(5, "3:1:6", blacklisted=True))
    snapshot = FarmController().snapshot(runtime)
    assert snapshot.state is FarmState.READY
    assert snapshot.eligible_count == 3
    assert snapshot.free_slots == 2


def test_one_wave_is_capped_by_live_free_slots_and_max_targets() -> None:
    runtime = Runtime()
    result = FarmController().run_one_wave(runtime, ship_count=25, max_targets=15)
    assert result.requested == 2
    assert result.attempted == 2
    assert result.verified == 2
    assert result.verified_targets == ("3:1:2", "3:1:3")
    assert len(runtime.calls) == 2
    assert all(call[2] == 25 and call[3].startswith("farm-") for call in runtime.calls)


def test_wave_stops_immediately_on_ambiguous_dispatch() -> None:
    runtime = Runtime()
    runtime.capacity = FleetCapacitySnapshot(used=19, maximum=22, free=3, source="fixture")
    runtime.unverified_target = "3:1:2"
    result = FarmController().run_one_wave(runtime, ship_count=25, max_targets=3)
    assert result.attempted == 1
    assert result.verified == 0
    assert len(runtime.calls) == 1
    assert "automatic retry is forbidden" in result.stopped_reason


def test_invalid_wave_parameters_fail_before_any_dispatch() -> None:
    runtime = Runtime()
    with pytest.raises(ValueError):
        FarmController().run_one_wave(runtime, ship_count=0, max_targets=1)
    with pytest.raises(ValueError):
        FarmController().run_one_wave(runtime, ship_count=25, max_targets=0)
    assert runtime.calls == []
