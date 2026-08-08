from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from v2.application.flight_source import (
    ActiveFlightSnapshot, FleetCapacitySnapshot, FlightSource, FlightSourceStatus, OfflineFlightSource,
)
from v2.application.live_flight_semantics import ClassifiedActiveFlight, build_live_flight_policy, classify_active_flights
from v2.application.live_overview import LiveOverviewSnapshot, build_live_overview
from v2.application.raid_actions import RaidActionService, RaidCommand, RaidDispatchResult, RaidPreparation
from v2.application.raid_journal import RaidActionRecord, RaidDispatchCoordinator
from v2.application.raid_reconciliation import RaidReconciliation, reconcile_unresolved_raids
from v2.application.read_store import (
    HistorySnapshot, OverviewSnapshot, QueueSnapshot, ReadOnlyStore, ReadStoreUnavailable,
    ReconSnapshot, TargetSnapshot,
)
from v2.application.v2_queue import V2QueueRepository
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database


@dataclass(frozen=True)
class DataSourceStatus:
    available: bool
    path: Path
    mode: str
    detail: str


def legacy_db_path(*, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if os.name == "nt" or "LOCALAPPDATA" in env:
        root = Path(env.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
        return root / "NemexiaRaidManager" / "nemexia.sqlite3"
    return user_home / ".nemexia_raid_manager" / "nemexia.sqlite3"


class V2ApplicationContext:
    """UI-facing migration context with isolated V2 writes and read-only legacy data."""

    def __init__(
        self, source_path: Path, *, flight_source: FlightSource | None = None,
        v2_settings: V2SettingsRepository | None = None,
        v2_database: V2Database | None = None,
        v2_queue: V2QueueRepository | None = None,
        raid_actions: RaidActionService | None = None,
    ) -> None:
        self.source_path = Path(source_path)
        self._store: ReadOnlyStore | None = None
        self._error: str | None = None
        self._flight_source: FlightSource = flight_source or OfflineFlightSource()
        self._v2_settings = v2_settings
        self._v2_database = v2_database
        self._v2_queue = v2_queue
        self._raid_actions = raid_actions
        self._last_flight_status: FlightSourceStatus | None = None
        self._live_snapshot_ready = False
        self._last_active_flights: tuple[ActiveFlightSnapshot, ...] = ()
        self._last_owned_planets: tuple[str, ...] = ()
        self._last_capacity: FleetCapacitySnapshot | None = None
        try:
            self._store = ReadOnlyStore(self.source_path)
        except ReadStoreUnavailable as exc:
            self._error = str(exc)

    @classmethod
    def auto_detect(cls, *, flight_source: FlightSource | None = None) -> "V2ApplicationContext":
        override = os.environ.get("NEMEXIA_V2_READ_DB", "").strip()
        source = Path(override).expanduser() if override else legacy_db_path()
        return cls(source, flight_source=flight_source)

    def close(self) -> None:
        if self._store is not None:
            self._store.close(); self._store = None
        closer = getattr(self._flight_source, "close", None)
        if callable(closer):
            closer()
        if self._raid_actions is not None:
            self._raid_actions.close(); self._raid_actions = None
        if self._v2_database is not None:
            self._v2_database.close(); self._v2_database = None

    def status(self) -> DataSourceStatus:
        if self._store is None:
            return DataSourceStatus(False, self.source_path, "read-only", self._error or "Read-only source is closed")
        store_status = self._store.status()
        return DataSourceStatus(True, store_status.path, "read-only", f"SQLite query_only={int(store_status.query_only)}")

    def overview(self) -> OverviewSnapshot:
        return OverviewSnapshot() if self._store is None else self._store.overview()

    def targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        return [] if self._store is None else self._store.list_targets(limit=limit)

    def history(self, *, limit: int = 1000) -> list[HistorySnapshot]:
        return [] if self._store is None else self._store.list_history(limit=limit)

    def recon(self, *, limit: int = 2000) -> list[ReconSnapshot]:
        return [] if self._store is None else self._store.list_recon(limit=limit)

    def plan(self, *, limit: int = 5000) -> list[QueueSnapshot]:
        if self._v2_queue is not None:
            return self._v2_queue.list(limit=limit)
        return [] if self._store is None else self._store.list_plan(limit=limit)

    def set_plan_state(self, queue_id: int, state: str) -> None:
        if self._v2_queue is None:
            raise RuntimeError("V2 raid queue is unavailable")
        self._v2_queue.set_state(queue_id, state)

    def legacy_setting(self, key: str, default: str | None = None) -> str | None:
        return default if self._store is None else self._store.get_setting(key, default)

    def v2_settings_available(self) -> bool:
        return self._v2_settings is not None

    def v2_setting(self, key: str, default: object = None) -> object:
        return default if self._v2_settings is None else self._v2_settings.get(key)

    def set_v2_setting(self, key: str, value: object) -> object:
        return self.set_v2_settings({key: value})[str(key)]

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        if self._v2_settings is None:
            raise RuntimeError("V2 settings storage is unavailable")
        parsed = self._v2_settings.set_many(values)
        if self._raid_actions is not None and "actions_enabled" in parsed:
            self._raid_actions.set_enabled(bool(parsed["actions_enabled"]))
        return parsed

    def v2_settings_snapshot(self) -> dict[str, object]:
        return {} if self._v2_settings is None else self._v2_settings.snapshot()

    def raid_actions_enabled(self) -> bool:
        return bool(self._raid_actions is not None and self._raid_actions.enabled)

    def _raid_command(self, target: str, player: str, ship_count: int) -> RaidCommand:
        return RaidCommand(
            target=target,
            player=player,
            ship_count=ship_count,
            home=str(self.v2_setting("farm_home", "")),
        )

    def prepare_raid(self, target: str, player: str, ship_count: int) -> RaidPreparation:
        if self._raid_actions is None:
            raise RuntimeError("V2 raid action service is unavailable")
        return self._raid_actions.prepare(self._raid_command(target, player, ship_count))

    def dispatch_plan_raid(
        self, *, queue_id: int, target: str, player: str, ship_count: int, request_id: str,
    ) -> RaidDispatchResult:
        if self._raid_actions is None or self._v2_database is None or self._v2_queue is None:
            raise RuntimeError("V2 raid dispatch services are unavailable")
        item = next((row for row in self.plan() if row.id == int(queue_id)), None)
        if item is None:
            raise RuntimeError(f"Queue row not found: {queue_id}")
        if item.coord != str(target):
            raise RuntimeError("Selected queue row changed; refresh Plan before sending")
        if item.state != "queued":
            raise RuntimeError(f"Queue row is not queued: {item.state}")
        if not item.enabled:
            raise RuntimeError(f"Target is disabled: {item.coord}")
        if item.blacklisted:
            raise RuntimeError(f"Target is blacklisted: {item.coord}")

        self._v2_queue.set_state(item.id, "sending")
        coordinator = RaidDispatchCoordinator(self._raid_actions, self._v2_database)
        try:
            result = coordinator.dispatch(
                self._raid_command(item.coord, item.player or player, ship_count),
                request_id=request_id,
            )
        except Exception:
            record = coordinator.record(request_id)
            if record is None:
                self._v2_queue.set_state(item.id, "queued")
            elif record.status == "ambiguous":
                self._v2_queue.set_state(item.id, "ambiguous")
            raise
        self._v2_queue.set_state(item.id, "sent" if result.verified else "ambiguous")
        return result

    def recent_raid_actions(self, *, limit: int = 200) -> list[RaidActionRecord]:
        if self._raid_actions is None or self._v2_database is None:
            return []
        return RaidDispatchCoordinator(self._raid_actions, self._v2_database).recent(limit=limit)

    def reconcile_raid_actions(self) -> list[RaidReconciliation]:
        """Resolve journal uncertainty only from the last explicit live refresh."""
        if (
            self._raid_actions is None
            or self._v2_database is None
            or self._v2_queue is None
            or not self._live_snapshot_ready
            or self._last_flight_status is None
            or not self._last_flight_status.available
        ):
            return []
        coordinator = RaidDispatchCoordinator(self._raid_actions, self._v2_database)
        resolved = reconcile_unresolved_raids(
            coordinator,
            coordinator.recent(limit=500),
            self.cached_classified_active_flights(),
        )
        for item in resolved:
            queue_matches = [
                row for row in self.plan()
                if row.coord == item.target and row.state in {"sending", "ambiguous"}
            ]
            # Never guess which queue row was responsible if duplicates exist.
            if len(queue_matches) == 1:
                self._v2_queue.set_state(queue_matches[0].id, "sent")
        return resolved

    def flight_status(self) -> FlightSourceStatus:
        self._last_flight_status = self._flight_source.status()
        return self._last_flight_status

    def cached_flight_status(self) -> FlightSourceStatus | None:
        return self._last_flight_status

    def refresh_live_source(self) -> FlightSourceStatus:
        refresher = getattr(self._flight_source, "refresh", None)
        if callable(refresher):
            refresher()
        status = self.flight_status()
        self._live_snapshot_ready = True
        self._last_active_flights = (); self._last_owned_planets = (); self._last_capacity = None
        if not status.available:
            return status
        try:
            self._last_active_flights = tuple(self._flight_source.flights())
            owned_reader = getattr(self._flight_source, "owned_planets", None)
            if callable(owned_reader):
                self._last_owned_planets = tuple(str(coord) for coord in owned_reader())
            capacity_reader = getattr(self._flight_source, "capacity", None)
            if callable(capacity_reader):
                self._last_capacity = capacity_reader()
        except Exception as exc:
            self._last_active_flights = (); self._last_owned_planets = (); self._last_capacity = None
            self._last_flight_status = FlightSourceStatus(False, f"Live-read остановлен: {exc}")
        return self._last_flight_status

    def active_flights(self) -> list[ActiveFlightSnapshot]:
        return list(self._last_active_flights) if self._live_snapshot_ready else list(self._flight_source.flights())

    def owned_planets(self) -> tuple[str, ...]:
        if self._live_snapshot_ready:
            return self._last_owned_planets
        reader = getattr(self._flight_source, "owned_planets", None)
        return tuple(reader()) if callable(reader) else ()

    def _flight_policy(self):
        if self._v2_settings is not None:
            farm_home = str(self._v2_settings.get("farm_home")); parts = farm_home.split(":")
            settings = {"home_g": parts[0], "home_s": parts[1], "home_p": parts[2]} if len(parts) == 3 else {}
            command_planets = (str(self._v2_settings.get("command_planet")),)
        else:
            settings = {key: self.legacy_setting(key) for key in ("home_g", "home_s", "home_p")}
            command_planets = ("2:5:6",)
        return build_live_flight_policy(settings, owned_planets=self.owned_planets(), command_planets=command_planets)

    def classified_active_flights(self) -> list[ClassifiedActiveFlight]:
        return list(classify_active_flights(self.active_flights(), self._flight_policy()))

    def cached_classified_active_flights(self) -> list[ClassifiedActiveFlight]:
        return [] if not self._live_snapshot_ready else list(classify_active_flights(self._last_active_flights, self._flight_policy()))

    def farm_blocking_flights(self) -> list[ClassifiedActiveFlight]:
        return [item for item in self.classified_active_flights() if item.facts.blocks_farm_cycle]

    def fleet_capacity(self) -> FleetCapacitySnapshot | None:
        if self._live_snapshot_ready:
            return self._last_capacity
        reader = getattr(self._flight_source, "capacity", None)
        return reader() if callable(reader) else None

    def live_overview_snapshot(self) -> LiveOverviewSnapshot:
        buffer = self._v2_settings.get("farm_return_buffer_minutes") if self._v2_settings is not None else self.legacy_setting("farm_return_buffer_minutes", "5")
        return build_live_overview(
            checked=self._live_snapshot_ready,
            status=self._last_flight_status,
            flights=self.cached_classified_active_flights(),
            capacity=self._last_capacity,
            return_buffer_minutes=buffer,
            persisted_farm_ready_at=self.legacy_setting("farm_next_cycle_at", ""),
        )
