from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from v2.application.flight_source import (
    ActiveFlightSnapshot,
    FleetCapacitySnapshot,
    FlightSource,
    FlightSourceStatus,
    OfflineFlightSource,
)
from v2.application.live_flight_semantics import (
    ClassifiedActiveFlight,
    build_live_flight_policy,
    classify_active_flights,
)
from v2.application.live_overview import LiveOverviewSnapshot, build_live_overview
from v2.application.read_store import (
    HistorySnapshot,
    OverviewSnapshot,
    QueueSnapshot,
    ReadOnlyStore,
    ReadStoreUnavailable,
    ReconSnapshot,
    TargetSnapshot,
)


@dataclass(frozen=True)
class DataSourceStatus:
    available: bool
    path: Path
    mode: str
    detail: str


def legacy_db_path(*, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Return the legacy SQLite location without creating any directories."""
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if os.name == "nt" or "LOCALAPPDATA" in env:
        root = Path(env.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
        return root / "NemexiaRaidManager" / "nemexia.sqlite3"
    return user_home / ".nemexia_raid_manager" / "nemexia.sqlite3"


class V2ApplicationContext:
    """UI-facing migration context with read-only data/live-source boundaries."""

    def __init__(self, source_path: Path, *, flight_source: FlightSource | None = None) -> None:
        self.source_path = Path(source_path)
        self._store: ReadOnlyStore | None = None
        self._error: str | None = None
        self._flight_source: FlightSource = flight_source or OfflineFlightSource()
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
            self._store.close()
            self._store = None
        closer = getattr(self._flight_source, "close", None)
        if callable(closer):
            closer()

    def status(self) -> DataSourceStatus:
        if self._store is None:
            return DataSourceStatus(
                available=False,
                path=self.source_path,
                mode="read-only",
                detail=self._error or "Read-only source is closed",
            )
        store_status = self._store.status()
        return DataSourceStatus(
            available=True,
            path=store_status.path,
            mode="read-only",
            detail=f"SQLite query_only={int(store_status.query_only)}",
        )

    def overview(self) -> OverviewSnapshot:
        return OverviewSnapshot() if self._store is None else self._store.overview()

    def targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        return [] if self._store is None else self._store.list_targets(limit=limit)

    def history(self, *, limit: int = 1000) -> list[HistorySnapshot]:
        return [] if self._store is None else self._store.list_history(limit=limit)

    def recon(self, *, limit: int = 2000) -> list[ReconSnapshot]:
        return [] if self._store is None else self._store.list_recon(limit=limit)

    def plan(self, *, limit: int = 5000) -> list[QueueSnapshot]:
        return [] if self._store is None else self._store.list_plan(limit=limit)

    def legacy_setting(self, key: str, default: str | None = None) -> str | None:
        if self._store is None:
            return default
        return self._store.get_setting(key, default)

    def flight_status(self) -> FlightSourceStatus:
        self._last_flight_status = self._flight_source.status()
        return self._last_flight_status

    def cached_flight_status(self) -> FlightSourceStatus | None:
        return self._last_flight_status

    def refresh_live_source(self) -> FlightSourceStatus:
        """Explicitly refresh and cache all read-only live facts as one UI snapshot."""
        refresher = getattr(self._flight_source, "refresh", None)
        if callable(refresher):
            refresher()
        status = self.flight_status()
        self._live_snapshot_ready = True
        self._last_active_flights = ()
        self._last_owned_planets = ()
        self._last_capacity = None
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
            self._last_active_flights = ()
            self._last_owned_planets = ()
            self._last_capacity = None
            self._last_flight_status = FlightSourceStatus(False, f"Live-read остановлен: {exc}")
        return self._last_flight_status

    def active_flights(self) -> list[ActiveFlightSnapshot]:
        if self._live_snapshot_ready:
            return list(self._last_active_flights)
        return list(self._flight_source.flights())

    def owned_planets(self) -> tuple[str, ...]:
        if self._live_snapshot_ready:
            return self._last_owned_planets
        reader = getattr(self._flight_source, "owned_planets", None)
        if not callable(reader):
            return ()
        return tuple(reader())

    def _flight_policy(self):
        settings = {
            key: self.legacy_setting(key)
            for key in ("home_g", "home_s", "home_p")
        }
        return build_live_flight_policy(settings, owned_planets=self.owned_planets())

    def classified_active_flights(self) -> list[ClassifiedActiveFlight]:
        return list(classify_active_flights(self.active_flights(), self._flight_policy()))

    def cached_classified_active_flights(self) -> list[ClassifiedActiveFlight]:
        if not self._live_snapshot_ready:
            return []
        return list(classify_active_flights(self._last_active_flights, self._flight_policy()))

    def farm_blocking_flights(self) -> list[ClassifiedActiveFlight]:
        return [item for item in self.classified_active_flights() if item.facts.blocks_farm_cycle]

    def fleet_capacity(self) -> FleetCapacitySnapshot | None:
        if self._live_snapshot_ready:
            return self._last_capacity
        capacity_reader = getattr(self._flight_source, "capacity", None)
        if not callable(capacity_reader):
            return None
        return capacity_reader()

    def live_overview_snapshot(self) -> LiveOverviewSnapshot:
        """Build Overview facts strictly from the last explicit live refresh."""
        return build_live_overview(
            checked=self._live_snapshot_ready,
            status=self._last_flight_status,
            flights=self.cached_classified_active_flights(),
            capacity=self._last_capacity,
            return_buffer_minutes=self.legacy_setting("farm_return_buffer_minutes", "5"),
            persisted_farm_ready_at=self.legacy_setting("farm_next_cycle_at", ""),
        )
