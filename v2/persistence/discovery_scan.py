from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from v2.persistence.database import V2Database, V2DatabaseError


DISCOVERY_SCHEMA_VERSION = 1
DISCOVERY_SYSTEM_COUNT = 120
_UNRESOLVED = ("running", "ambiguous")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def install_discovery_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS discovery_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    row = conn.execute(
        "SELECT COALESCE(MAX(version),0) FROM discovery_schema_migrations"
    ).fetchone()
    current = int(row[0]) if row else 0
    if current > DISCOVERY_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"Discovery schema {current} is newer than supported {DISCOVERY_SCHEMA_VERSION}"
        )
    if current < 1:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS discovery_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN (
                    'running','stopped','completed','ambiguous','failed_safe'
                )),
                cursor_index INTEGER NOT NULL DEFAULT 0,
                account_fingerprint TEXT NOT NULL,
                planet_id TEXT NOT NULL,
                planet_coord TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_discovery_scan_status
                ON discovery_scans(status, id DESC);
            CREATE TABLE IF NOT EXISTS discovery_scan_systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL,
                sequence_index INTEGER NOT NULL,
                galaxy INTEGER NOT NULL,
                solar INTEGER NOT NULL,
                asteroid_count INTEGER NOT NULL,
                debris_count INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(scan_id, sequence_index),
                UNIQUE(scan_id, galaxy, solar),
                FOREIGN KEY(scan_id) REFERENCES discovery_scans(scan_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_discovery_system_scan
                ON discovery_scan_systems(scan_id, sequence_index);
            """
        )
        conn.execute(
            "INSERT INTO discovery_schema_migrations(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )


@dataclass(frozen=True)
class DiscoveryScanRecord:
    scan_id: str
    status: str
    cursor_index: int
    account_fingerprint: str
    planet_id: str
    planet_coord: str
    detail: str
    created_at: str
    updated_at: str
    completed_at: str | None

    @property
    def completed_systems(self) -> int:
        return self.cursor_index

    @property
    def done(self) -> bool:
        return self.status == "completed" and self.cursor_index == DISCOVERY_SYSTEM_COUNT


@dataclass(frozen=True)
class DiscoverySystemRecord:
    scan_id: str
    sequence_index: int
    galaxy: int
    solar: int
    asteroid_count: int
    debris_count: int
    observed_at: str


class DiscoveryScanConflictError(RuntimeError):
    pass


class DiscoveryScanRepository:
    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_discovery_schema(conn)

    @staticmethod
    def _scan(row: sqlite3.Row | None) -> DiscoveryScanRecord | None:
        if row is None:
            return None
        return DiscoveryScanRecord(
            scan_id=str(row["scan_id"]),
            status=str(row["status"]),
            cursor_index=int(row["cursor_index"]),
            account_fingerprint=str(row["account_fingerprint"]),
            planet_id=str(row["planet_id"]),
            planet_coord=str(row["planet_coord"]),
            detail=str(row["detail"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            completed_at=(str(row["completed_at"]) if row["completed_at"] is not None else None),
        )

    @staticmethod
    def _system(row: sqlite3.Row) -> DiscoverySystemRecord:
        return DiscoverySystemRecord(
            scan_id=str(row["scan_id"]),
            sequence_index=int(row["sequence_index"]),
            galaxy=int(row["galaxy"]),
            solar=int(row["solar"]),
            asteroid_count=int(row["asteroid_count"]),
            debris_count=int(row["debris_count"]),
            observed_at=str(row["observed_at"]),
        )

    def read(self, scan_id: str) -> DiscoveryScanRecord | None:
        row = self.database._require_conn().execute(
            "SELECT * FROM discovery_scans WHERE scan_id=?",
            (str(scan_id),),
        ).fetchone()
        return self._scan(row)

    def unresolved(self) -> tuple[DiscoveryScanRecord, ...]:
        rows = self.database._require_conn().execute(
            """SELECT * FROM discovery_scans
               WHERE status IN ('running','ambiguous') ORDER BY id DESC"""
        ).fetchall()
        return tuple(item for row in rows if (item := self._scan(row)) is not None)

    def begin(
        self,
        *,
        scan_id: str,
        account_fingerprint: str,
        planet_id: str,
        planet_coord: str,
    ) -> DiscoveryScanRecord:
        scan_id = str(scan_id or "").strip()
        if not scan_id:
            raise V2DatabaseError("discovery scan_id is required")
        if self.read(scan_id) is not None:
            raise DiscoveryScanConflictError(f"Discovery scan already exists: {scan_id}")
        unresolved = self.unresolved()
        if unresolved:
            raise DiscoveryScanConflictError(
                f"Discovery scan blocked by unresolved {unresolved[0].scan_id} ({unresolved[0].status})"
            )
        now = _now()
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """INSERT INTO discovery_scans(
                    scan_id,status,cursor_index,account_fingerprint,planet_id,planet_coord,
                    created_at,updated_at
                ) VALUES(?, 'running', 0, ?, ?, ?, ?, ?)""",
                (
                    scan_id,
                    str(account_fingerprint),
                    str(planet_id),
                    str(planet_coord),
                    now,
                    now,
                ),
            )
        record = self.read(scan_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Discovery scan disappeared after insert: {scan_id}")
        return record

    def resume(self, scan_id: str) -> DiscoveryScanRecord:
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE discovery_scans SET status='running', detail='', updated_at=?
                   WHERE scan_id=? AND status IN ('stopped','failed_safe')""",
                (_now(), str(scan_id)),
            )
        if cursor.rowcount != 1:
            raise DiscoveryScanConflictError(
                "Only stopped/failed_safe discovery scans can be resumed automatically"
            )
        record = self.read(scan_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Discovery scan disappeared after resume: {scan_id}")
        return record

    def record_system(
        self,
        *,
        scan_id: str,
        sequence_index: int,
        galaxy: int,
        solar: int,
        asteroid_count: int,
        debris_count: int,
        observed_at: str,
    ) -> DiscoveryScanRecord:
        sequence_index = int(sequence_index)
        scan = self.read(scan_id)
        if scan is None:
            raise V2DatabaseError(f"Discovery scan not found: {scan_id}")
        if scan.status != "running":
            raise DiscoveryScanConflictError(
                f"Discovery scan is not running: {scan.scan_id} ({scan.status})"
            )
        if scan.cursor_index != sequence_index:
            raise DiscoveryScanConflictError(
                f"Discovery cursor mismatch: expected {scan.cursor_index}, got {sequence_index}"
            )
        if not 0 <= sequence_index < DISCOVERY_SYSTEM_COUNT:
            raise V2DatabaseError(f"Invalid discovery sequence index: {sequence_index}")

        conn = self.database._require_conn()
        now = _now()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO discovery_scan_systems(
                        scan_id,sequence_index,galaxy,solar,asteroid_count,debris_count,
                        observed_at,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        str(scan_id),
                        sequence_index,
                        int(galaxy),
                        int(solar),
                        max(0, int(asteroid_count)),
                        max(0, int(debris_count)),
                        str(observed_at),
                        now,
                    ),
                )
                conn.execute(
                    """UPDATE discovery_scans
                       SET cursor_index=?, updated_at=?, detail=''
                       WHERE scan_id=? AND status='running'""",
                    (sequence_index + 1, now, str(scan_id)),
                )
        except sqlite3.IntegrityError as exc:
            raise DiscoveryScanConflictError(
                f"Discovery system evidence already exists for {scan_id} index {sequence_index}"
            ) from exc
        record = self.read(scan_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Discovery scan disappeared: {scan_id}")
        return record

    def finish_safe(self, scan_id: str, *, status: str, detail: str) -> DiscoveryScanRecord:
        if status not in {"stopped", "failed_safe", "ambiguous"}:
            raise V2DatabaseError(f"Invalid discovery non-complete status: {status}")
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE discovery_scans SET status=?, detail=?, updated_at=?
                   WHERE scan_id=? AND status='running'""",
                (status, str(detail or ""), _now(), str(scan_id)),
            )
        if cursor.rowcount != 1:
            raise DiscoveryScanConflictError(f"Running discovery scan not found: {scan_id}")
        record = self.read(scan_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Discovery scan disappeared: {scan_id}")
        return record

    def complete(self, scan_id: str) -> DiscoveryScanRecord:
        scan = self.read(scan_id)
        if scan is None or scan.status != "running":
            raise DiscoveryScanConflictError(f"Running discovery scan not found: {scan_id}")
        count = int(
            self.database._require_conn().execute(
                "SELECT COUNT(*) FROM discovery_scan_systems WHERE scan_id=?",
                (str(scan_id),),
            ).fetchone()[0]
        )
        if scan.cursor_index != DISCOVERY_SYSTEM_COUNT or count != DISCOVERY_SYSTEM_COUNT:
            raise DiscoveryScanConflictError(
                f"Discovery scan is incomplete: cursor={scan.cursor_index}, systems={count}"
            )
        now = _now()
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE discovery_scans
                   SET status='completed', detail='', completed_at=?, updated_at=?
                   WHERE scan_id=? AND status='running'""",
                (now, now, str(scan_id)),
            )
        record = self.read(scan_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Discovery scan disappeared: {scan_id}")
        return record

    def systems(self, scan_id: str) -> tuple[DiscoverySystemRecord, ...]:
        rows = self.database._require_conn().execute(
            """SELECT * FROM discovery_scan_systems
               WHERE scan_id=? ORDER BY sequence_index""",
            (str(scan_id),),
        ).fetchall()
        return tuple(self._system(row) for row in rows)

    def last_completed(self) -> DiscoveryScanRecord | None:
        row = self.database._require_conn().execute(
            """SELECT * FROM discovery_scans
               WHERE status='completed' AND cursor_index=?
               ORDER BY completed_at DESC, id DESC LIMIT 1""",
            (DISCOVERY_SYSTEM_COUNT,),
        ).fetchone()
        return self._scan(row)
