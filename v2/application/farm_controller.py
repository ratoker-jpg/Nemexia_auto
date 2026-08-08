from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from v2.application.flight_source import FleetCapacitySnapshot, FlightSourceStatus
from v2.application.live_overview import LiveOverviewSnapshot
from v2.application.raid_actions import RaidDispatchResult
from v2.application.raid_journal import RaidActionRecord
from v2.application.read_store import QueueSnapshot


class FarmState(str, Enum):
    ACTIONS_DISABLED = "actions_disabled"
    LIVE_NOT_CHECKED = "live_not_checked"
    LIVE_UNAVAILABLE = "live_unavailable"
    BLOCKED_UNRESOLVED = "blocked_unresolved"
    WAITING_RETURN = "waiting_return"
    WAITING_CAPACITY = "waiting_capacity"
    NO_TARGETS = "no_targets"
    READY = "ready"


@dataclass(frozen=True)
class FarmSnapshot:
    state: FarmState
    detail: str
    eligible_count: int
    free_slots: int
    blocking_attacks: int
    unresolved_actions: int
    ready_at: str | None = None


@dataclass(frozen=True)
class FarmWaveResult:
    requested: int
    attempted: int
    verified: int
    verified_targets: tuple[str, ...]
    stopped_reason: str


class FarmRuntime(Protocol):
    def raid_actions_enabled(self) -> bool: ...
    def cached_flight_status(self) -> FlightSourceStatus | None: ...
    def fleet_capacity(self) -> FleetCapacitySnapshot | None: ...
    def farm_blocking_flights(self) -> list[object]: ...
    def live_overview_snapshot(self) -> LiveOverviewSnapshot: ...
    def plan(self, *, limit: int = 5000) -> list[QueueSnapshot]: ...
    def recent_raid_actions(self, *, limit: int = 200) -> list[RaidActionRecord]: ...
    def dispatch_plan_raid(
        self, *, queue_id: int, target: str, player: str, ship_count: int, request_id: str,
    ) -> RaidDispatchResult: ...


def eligible_queue(items: Sequence[QueueSnapshot]) -> list[QueueSnapshot]:
    return [
        item for item in items
        if item.state == "queued" and item.enabled and not item.blacklisted
    ]


class FarmController:
    """Typed V2 farm policy; UI text never drives farm decisions."""

    def snapshot(self, runtime: FarmRuntime) -> FarmSnapshot:
        items = eligible_queue(runtime.plan())
        status = runtime.cached_flight_status()
        capacity = runtime.fleet_capacity() if status is not None and status.available else None
        free_slots = max(0, int(capacity.free)) if capacity is not None else 0
        blocking = len(runtime.farm_blocking_flights()) if status is not None and status.available else 0
        overview = runtime.live_overview_snapshot() if status is not None and status.available else None
        ready_at = overview.inferred_farm_ready_at if overview is not None else None
        unresolved = [
            item for item in runtime.recent_raid_actions(limit=500)
            if item.status in {"pending", "ambiguous"}
        ]

        if not runtime.raid_actions_enabled():
            return FarmSnapshot(
                FarmState.ACTIONS_DISABLED,
                "Действия V2 выключены в Настройках.",
                len(items), free_slots, blocking, len(unresolved), ready_at,
            )
        if status is None:
            return FarmSnapshot(
                FarmState.LIVE_NOT_CHECKED,
                "Сначала обнови live-полёты.",
                len(items), 0, 0, len(unresolved), None,
            )
        if not status.available or capacity is None:
            return FarmSnapshot(
                FarmState.LIVE_UNAVAILABLE,
                status.detail or "Live-полёты или capacity недоступны.",
                len(items), 0, 0, len(unresolved), None,
            )
        if unresolved:
            return FarmSnapshot(
                FarmState.BLOCKED_UNRESOLVED,
                f"Есть unresolved отправки: {len(unresolved)}. Сначала сверка через «Активные».",
                len(items), free_slots, blocking, len(unresolved), ready_at,
            )
        if blocking:
            suffix = f" Следующая проверка после {ready_at}." if ready_at else ""
            return FarmSnapshot(
                FarmState.WAITING_RETURN,
                f"Есть farm-blocking атаки: {blocking}. Новую волну пока не запускаем.{suffix}",
                len(items), free_slots, blocking, 0, ready_at,
            )
        if free_slots <= 0:
            return FarmSnapshot(
                FarmState.WAITING_CAPACITY,
                "Свободных fleet slots нет.",
                len(items), 0, 0, 0, ready_at,
            )
        if not items:
            return FarmSnapshot(
                FarmState.NO_TARGETS,
                "В V2-очереди нет eligible queued целей.",
                0, free_slots, 0, 0, ready_at,
            )
        return FarmSnapshot(
            FarmState.READY,
            f"Готово к волне: целей {len(items)}, свободных слотов {free_slots}.",
            len(items), free_slots, 0, 0, ready_at,
        )

    def run_one_wave(
        self,
        runtime: FarmRuntime,
        *,
        ship_count: int,
        max_targets: int,
    ) -> FarmWaveResult:
        if int(ship_count) <= 0:
            raise ValueError("ship_count must be > 0")
        if int(max_targets) <= 0:
            raise ValueError("max_targets must be > 0")
        snapshot = self.snapshot(runtime)
        if snapshot.state is not FarmState.READY:
            raise RuntimeError(snapshot.detail)

        targets = eligible_queue(runtime.plan())
        requested = min(snapshot.free_slots, int(max_targets), len(targets))
        verified_targets: list[str] = []
        attempted = 0
        stopped_reason = "wave complete"

        for item in targets[:requested]:
            request_id = f"farm-{uuid.uuid4().hex}"
            attempted += 1
            try:
                result = runtime.dispatch_plan_raid(
                    queue_id=item.id,
                    target=item.coord,
                    player=item.player,
                    ship_count=int(ship_count),
                    request_id=request_id,
                )
            except Exception as exc:
                stopped_reason = f"stopped after {item.coord}: {exc}"
                break
            if not result.verified:
                stopped_reason = (
                    f"stopped after ambiguous {item.coord}; automatic retry is forbidden"
                )
                break
            verified_targets.append(item.coord)

        return FarmWaveResult(
            requested=requested,
            attempted=attempted,
            verified=len(verified_targets),
            verified_targets=tuple(verified_targets),
            stopped_reason=stopped_reason,
        )
