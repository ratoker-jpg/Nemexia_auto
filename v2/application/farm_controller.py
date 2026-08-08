from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    NEED_RECON = "need_recon"
    # Compatibility alias for callers compiled against V2-40. New logic must use NEED_RECON.
    NO_TARGETS = "need_recon"
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
    def v2_setting(self, key: str, default: object = None) -> object: ...
    def plan(self, *, limit: int = 5000) -> list[QueueSnapshot]: ...
    def recent_raid_actions(self, *, limit: int = 200) -> list[RaidActionRecord]: ...
    def recent_spy_actions(self, *, limit: int = 200) -> list[object]: ...
    def dispatch_plan_raid(
        self, *, queue_id: int, target: str, player: str, ship_count: int, request_id: str,
    ) -> RaidDispatchResult: ...


def eligible_queue(items: Sequence[QueueSnapshot]) -> list[QueueSnapshot]:
    return [item for item in items if item.state == "queued" and item.enabled and not item.blacklisted]


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.replace(microsecond=0).isoformat() if value is not None else None


def _return_buffer_minutes(runtime: FarmRuntime) -> int:
    try:
        value = int(str(runtime.v2_setting("farm_return_buffer_minutes", 5)).strip())
    except (AttributeError, TypeError, ValueError):
        value = 5
    return max(0, min(60, value))


def _journal_ready_at(actions: Sequence[RaidActionRecord], *, buffer_minutes: int) -> datetime | None:
    deadlines: list[datetime] = []
    for item in actions:
        if item.status != "verified" or not item.request_id.startswith("farm-"):
            continue
        returned = _parse_dt(item.return_at)
        if returned is not None:
            deadlines.append(returned + timedelta(minutes=buffer_minutes))
    return max(deadlines, default=None)


def _recent_spy_actions(runtime: FarmRuntime, *, limit: int = 500) -> list[object]:
    reader = getattr(runtime, "recent_spy_actions", None)
    if not callable(reader):
        return []
    try:
        return list(reader(limit=limit))
    except Exception:
        # Losing access to the persisted spy journal must not create a new send window.
        return [_UnreadableSpyJournal()]


class _UnreadableSpyJournal:
    status = "pending"


class FarmController:
    """Typed V2 farm policy; UI text never drives farm decisions."""

    def snapshot(self, runtime: FarmRuntime) -> FarmSnapshot:
        items = eligible_queue(runtime.plan())
        status = runtime.cached_flight_status()
        capacity = runtime.fleet_capacity() if status is not None and status.available else None
        free_slots = max(0, int(capacity.free)) if capacity is not None else 0
        blocking = len(runtime.farm_blocking_flights()) if status is not None and status.available else 0
        overview = runtime.live_overview_snapshot() if status is not None and status.available else None
        actions = runtime.recent_raid_actions(limit=500)
        unresolved_raid = [item for item in actions if item.status in {"pending", "ambiguous"}]
        spy_actions = _recent_spy_actions(runtime, limit=500)
        unresolved_spy = [
            item for item in spy_actions
            if str(getattr(item, "status", "")) in {"pending", "ambiguous"}
        ]
        unresolved_count = len(unresolved_raid) + len(unresolved_spy)

        live_ready = _parse_dt(overview.inferred_farm_ready_at) if overview is not None else None
        journal_ready = _journal_ready_at(actions, buffer_minutes=_return_buffer_minutes(runtime))
        deadlines = [value for value in (live_ready, journal_ready) if value is not None]
        ready_deadline = max(deadlines, default=None)
        ready_at = _iso(ready_deadline)

        if not runtime.raid_actions_enabled():
            return FarmSnapshot(FarmState.ACTIONS_DISABLED, "Действия V2 выключены в Настройках.", len(items), free_slots, blocking, unresolved_count, ready_at)
        if status is None:
            return FarmSnapshot(FarmState.LIVE_NOT_CHECKED, "Сначала обнови live-полёты.", len(items), 0, 0, unresolved_count, ready_at)
        if not status.available or capacity is None:
            return FarmSnapshot(FarmState.LIVE_UNAVAILABLE, status.detail or "Live-полёты или capacity недоступны.", len(items), 0, 0, unresolved_count, ready_at)
        if unresolved_count:
            detail = (
                f"Есть unresolved side effects: raid={len(unresolved_raid)}, spy={len(unresolved_spy)}. "
                "Новый raid/recon цикл заблокирован до ручной сверки."
            )
            return FarmSnapshot(FarmState.BLOCKED_UNRESOLVED, detail, len(items), free_slots, blocking, unresolved_count, ready_at)
        if blocking:
            suffix = f" Следующая проверка после {ready_at}." if ready_at else ""
            return FarmSnapshot(FarmState.WAITING_RETURN, f"Есть farm-blocking атаки: {blocking}. Новую волну пока не запускаем.{suffix}", len(items), free_slots, blocking, 0, ready_at)
        if not items:
            return FarmSnapshot(
                FarmState.NEED_RECON,
                "V2-очередь исчерпана: нужна контролируемая свежая разведка и refill.",
                0,
                free_slots,
                0,
                0,
                ready_at,
            )
        if ready_deadline is not None and datetime.now(timezone.utc) < ready_deadline:
            return FarmSnapshot(FarmState.WAITING_RETURN, f"Farm-return завершён, действует return-buffer до {ready_at}.", len(items), free_slots, 0, 0, ready_at)
        if free_slots <= 0:
            return FarmSnapshot(FarmState.WAITING_CAPACITY, "Свободных fleet slots нет.", len(items), 0, 0, 0, ready_at)
        return FarmSnapshot(FarmState.READY, f"Готово к волне: целей {len(items)}, свободных слотов {free_slots}.", len(items), free_slots, 0, 0, ready_at)

    def run_one_wave(self, runtime: FarmRuntime, *, ship_count: int, max_targets: int) -> FarmWaveResult:
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
                result = runtime.dispatch_plan_raid(queue_id=item.id, target=item.coord, player=item.player, ship_count=int(ship_count), request_id=request_id)
            except Exception as exc:
                stopped_reason = f"stopped after {item.coord}: {exc}"
                break
            if not result.verified:
                stopped_reason = f"stopped after ambiguous {item.coord}; automatic retry is forbidden"
                break
            verified_targets.append(item.coord)

        return FarmWaveResult(
            requested=requested,
            attempted=attempted,
            verified=len(verified_targets),
            verified_targets=tuple(verified_targets),
            stopped_reason=stopped_reason,
        )
