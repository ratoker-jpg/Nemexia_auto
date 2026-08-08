from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


class ReadStoreUnavailable(RuntimeError):
    """Raised when a requested read-only data source cannot be opened safely."""


@dataclass(frozen=True)
class OverviewSnapshot:
    targets_total: int = 0
    targets_enabled: int = 0
    queue_queued: int = 0
    history_total: int = 0
    latest_raid_at: str | None = None
    latest_spy_at: str | None = None


@dataclass(frozen=True)
class TargetSnapshot:
    coord: str
    player: str
    energy: int
    enabled: bool
    blacklisted: bool
    notes: str
    metal: int | None
    minerals: int | None
    gas: int | None
    last_spy_at: str | None
    raid_count: int
    last_raid_at: str | None
    last_return_at: str | None


@dataclass(frozen=True)
class HistorySnapshot:
    id: int
    source: str | None
    target: str
    player: str | None
    ship_count: int | None
    sent_at: str
    arrival_at: str | None
    return_at: str | None
    status: str
    error: str | None


@dataclass(frozen=True)
class ReconSnapshot:
    id: int
    target_coord: str
    report_at: str | None
    energy: int | None
    metal: int | None
    minerals: int | None
    gas: int | None
    population: int | None
    ships: int | None
    defense: int | None
    completeness: str | None
    source: str


@dataclass(frozen=True)
class QueueSnapshot:
    id: int
    position: int
    state: str
    coord: str
    player: str
    metal: int | None
    minerals: int | None
    gas: int | None
    last_spy_at: str | None
    enabled: bool
    blacklisted: bool


@dataclass(frozen=True)
class StoreStatus:
    path: Path
    query_only: bool
    tables: frozenset[str]


_REQUIRED_TABLES = frozenset({"targets", "history", "queue"})


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


class ReadOnlyStore:
    """Read legacy Nemexia data without initializing or mutating its schema."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ReadStoreUnavailable(f"SQLite file not found: {self.path}")
        try:
            self._conn = sqlite3.connect(_readonly_uri(self.path), uri=True)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA query_only=ON")
            tables = self._table_names()
        except sqlite3.Error as exc:
            raise ReadStoreUnavailable(f"Cannot open SQLite read-only: {self.path}") from exc
        missing = _REQUIRED_TABLES - tables
        if missing:
            self.close()
            names = ", ".join(sorted(missing))
            raise ReadStoreUnavailable(f"Required tables are missing: {names}")

    def __enter__(self) -> "ReadOnlyStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
            self._conn = None

    def _table_names(self) -> frozenset[str]:
        rows = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return frozenset(str(row[0]) for row in rows)

    def status(self) -> StoreStatus:
        if self._conn is None:
            raise ReadStoreUnavailable("Read-only store is closed")
        query_only = bool(self._conn.execute("PRAGMA query_only").fetchone()[0])
        return StoreStatus(self.path, query_only, self._table_names())

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Read one persisted legacy setting without creating the settings table."""
        if "settings" not in self._table_names():
            return default
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (str(key),)).fetchone()
        return str(row[0]) if row is not None else default

    def overview(self) -> OverviewSnapshot:
        target_row = self._conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN enabled=1 AND blacklisted=0 THEN 1 ELSE 0 END), 0) AS enabled,
                   MAX(last_spy_at) AS latest_spy_at
            FROM targets
            """
        ).fetchone()
        queued = self._conn.execute("SELECT COUNT(*) FROM queue WHERE state='queued'").fetchone()[0]
        history_row = self._conn.execute(
            "SELECT COUNT(*) AS total, MAX(sent_at) AS latest_raid_at FROM history"
        ).fetchone()
        return OverviewSnapshot(
            targets_total=int(target_row["total"] or 0),
            targets_enabled=int(target_row["enabled"] or 0),
            queue_queued=int(queued or 0),
            history_total=int(history_row["total"] or 0),
            latest_raid_at=history_row["latest_raid_at"],
            latest_spy_at=target_row["latest_spy_at"],
        )

    def list_targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        rows = self._conn.execute(
            """
            SELECT coord, player, energy, enabled, blacklisted, notes,
                   metal, minerals, resource_gas, last_spy_at, raid_count,
                   last_raid_at, last_return_at
            FROM targets
            ORDER BY g, s, p
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [
            TargetSnapshot(
                coord=str(row["coord"]), player=str(row["player"] or "—"),
                energy=int(row["energy"] or 0), enabled=bool(row["enabled"]),
                blacklisted=bool(row["blacklisted"]), notes=str(row["notes"] or ""),
                metal=row["metal"], minerals=row["minerals"], gas=row["resource_gas"],
                last_spy_at=row["last_spy_at"], raid_count=int(row["raid_count"] or 0),
                last_raid_at=row["last_raid_at"], last_return_at=row["last_return_at"],
            )
            for row in rows
        ]

    def list_history(self, *, limit: int = 1000) -> list[HistorySnapshot]:
        rows = self._conn.execute(
            """
            SELECT id, source, target, player, ship_count, sent_at,
                   arrival_at, return_at, status, error
            FROM history
            ORDER BY sent_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [
            HistorySnapshot(
                id=int(row["id"]), source=row["source"], target=str(row["target"]),
                player=row["player"], ship_count=row["ship_count"], sent_at=str(row["sent_at"]),
                arrival_at=row["arrival_at"], return_at=row["return_at"],
                status=str(row["status"]), error=row["error"],
            )
            for row in rows
        ]

    def list_recon(self, *, limit: int = 2000) -> list[ReconSnapshot]:
        """Return persisted spy reports newest first; never trigger a live refresh."""
        if "spy_reports" not in self._table_names():
            return []
        rows = self._conn.execute(
            """
            SELECT id, target_coord, report_at, energy, metal, minerals, gas,
                   population, ships, defense, completeness, source
            FROM spy_reports
            ORDER BY COALESCE(report_at, imported_at) DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [
            ReconSnapshot(
                id=int(row["id"]), target_coord=str(row["target_coord"]),
                report_at=row["report_at"], energy=row["energy"], metal=row["metal"],
                minerals=row["minerals"], gas=row["gas"], population=row["population"],
                ships=row["ships"], defense=row["defense"], completeness=row["completeness"],
                source=str(row["source"] or "messages"),
            )
            for row in rows
        ]

    def list_plan(self, *, limit: int = 5000) -> list[QueueSnapshot]:
        """Return the persisted queue exactly as it exists, without regenerating it."""
        rows = self._conn.execute(
            """
            SELECT q.id, q.position, q.state, q.coord,
                   t.player, t.metal, t.minerals, t.resource_gas, t.last_spy_at,
                   t.enabled, t.blacklisted
            FROM queue q
            LEFT JOIN targets t ON t.coord=q.coord
            ORDER BY CASE WHEN q.state='queued' THEN 0 ELSE 1 END, q.position, q.id
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [
            QueueSnapshot(
                id=int(row["id"]), position=int(row["position"]), state=str(row["state"]),
                coord=str(row["coord"]), player=str(row["player"] or "—"),
                metal=row["metal"], minerals=row["minerals"], gas=row["resource_gas"],
                last_spy_at=row["last_spy_at"], enabled=bool(row["enabled"]),
                blacklisted=bool(row["blacklisted"]),
            )
            for row in rows
        ]
