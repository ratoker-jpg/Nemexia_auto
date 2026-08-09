from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from v2.persistence.database import V2Database, V2DatabaseError


ASTEROID_AUTORENEW_SCHEMA_VERSION = 2
ASTEROID_AUTORENEW_STATUSES = frozenset(
    {
        "disarmed",
        "disarmed_restart",
        "armed_due",
        "running_discovery",
        "running_dispatch",
        "waiting_return",
        "stopped_manual",
        "stopped_no_asteroids",
        "stopped_capacity",
        "stopped_insufficient",
        "stopped_captcha",
        "stopped_ambiguous",
        "blocked",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def install_asteroid_autorenew_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS asteroid_autorenew_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    row = conn.execute(
        "SELECT COALESCE(MAX(version),0) FROM asteroid_autorenew_schema_migrations"
    ).fetchone()
    current = int(row[0]) if row else 0
    if current > ASTEROID_AUTORENEW_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"Asteroid autorenew schema {current} is newer than supported "
            f"{ASTEROID_AUTORENEW_SCHEMA_VERSION}"
        )
    if current < 1:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS asteroid_autorenew_state (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                status TEXT NOT NULL,
                armed INTEGER NOT NULL CHECK(armed IN (0,1)),
                session_id TEXT NOT NULL DEFAULT '',
                source_planet_id TEXT NOT NULL DEFAULT '',
                source_coord TEXT NOT NULL DEFAULT '',
                account_fingerprint TEXT NOT NULL DEFAULT '',
                recycler_count INTEGER NOT NULL DEFAULT 5 CHECK(recycler_count > 0),
                max_flights INTEGER NOT NULL DEFAULT 15 CHECK(max_flights > 0),
                safety_seconds INTEGER NOT NULL DEFAULT 10 CHECK(safety_seconds >= 0),
                buffer_minutes INTEGER NOT NULL DEFAULT 5 CHECK(buffer_minutes >= 0),
                next_cycle_at TEXT,
                active_scan_id TEXT,
                cycle_started_at TEXT,
                last_return_at TEXT,
                verified_sent INTEGER NOT NULL DEFAULT 0 CHECK(verified_sent >= 0),
                detail TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );"""
        )
        conn.execute(
            """INSERT OR IGNORE INTO asteroid_autorenew_state(
                singleton_id,status,armed,updated_at
            ) VALUES(1,'disarmed',0,?)""",
            (_now(),),
        )
        conn.execute(
            "INSERT INTO asteroid_autorenew_schema_migrations(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )
        current = 1
    if current < 2:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS asteroid_autorenew_scan_observations (
                scan_id TEXT NOT NULL,
                sequence_index INTEGER NOT NULL CHECK(sequence_index BETWEEN 0 AND 119),
                observation_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(scan_id, observation_id),
                FOREIGN KEY(observation_id) REFERENCES asteroid_observations(id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_autorenew_scan_observations_sequence
                ON asteroid_autorenew_scan_observations(scan_id, sequence_index, observation_id);"""
        )
        conn.execute(
            "INSERT INTO asteroid_autorenew_schema_migrations(version, applied_at) VALUES(2, ?)",
            (_now(),),
        )


@dataclass(frozen=True)
class AsteroidAutorenewState:
    status: str
    armed: bool
    session_id: str
    source_planet_id: str
    source_coord: str
    account_fingerprint: str
    recycler_count: int
    max_flights: int
    safety_seconds: int
    buffer_minutes: int
    next_cycle_at: str | None
    active_scan_id: str | None
    cycle_started_at: str | None
    last_return_at: str | None
    verified_sent: int
    detail: str
    updated_at: str

    @property
    def due_at(self) -> datetime | None:
        if not self.next_cycle_at:
            return None
        parsed = datetime.fromisoformat(self.next_cycle_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class AsteroidAutorenewRepository:
    """Component-versioned V2-owned scheduler state and scan provenance.

    `armed` is persisted only for crash diagnostics. Service construction always
    disarms stale authority, so persisted armed state can never authorize a new
    browser mutation in a later process. Unresolved discovery identity is retained
    across scheduler stops/restarts so uncertainty can never be erased by disarm.
    """

    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_asteroid_autorenew_schema(conn)

    @staticmethod
    def _state(row: sqlite3.Row) -> AsteroidAutorenewState:
        return AsteroidAutorenewState(
            status=str(row["status"]),
            armed=bool(row["armed"]),
            session_id=str(row["session_id"] or ""),
            source_planet_id=str(row["source_planet_id"] or ""),
            source_coord=str(row["source_coord"] or ""),
            account_fingerprint=str(row["account_fingerprint"] or ""),
            recycler_count=int(row["recycler_count"]),
            max_flights=int(row["max_flights"]),
            safety_seconds=int(row["safety_seconds"]),
            buffer_minutes=int(row["buffer_minutes"]),
            next_cycle_at=str(row["next_cycle_at"]) if row["next_cycle_at"] else None,
            active_scan_id=str(row["active_scan_id"]) if row["active_scan_id"] else None,
            cycle_started_at=str(row["cycle_started_at"]) if row["cycle_started_at"] else None,
            last_return_at=str(row["last_return_at"]) if row["last_return_at"] else None,
            verified_sent=int(row["verified_sent"]),
            detail=str(row["detail"] or ""),
            updated_at=str(row["updated_at"]),
        )

    def read(self) -> AsteroidAutorenewState:
        row = self.database._require_conn().execute(
            "SELECT * FROM asteroid_autorenew_state WHERE singleton_id=1"
        ).fetchone()
        if row is None:  # pragma: no cover - schema installation guarantees the row
            raise V2DatabaseError("Asteroid autorenew singleton state is missing")
        return self._state(row)

    def _unresolved_active_scan_id(self, scan_id: str | None) -> str | None:
        """Return the exact unresolved AUTO-11 discovery identity, including crash orphans.

        Normal execution records `active_scan_id` immediately after creating the
        AUTO-10 row. A process can still die in that tiny gap. Because AUTO-10 permits
        at most one globally unresolved scan, an unresolved `autorenew-scan:*` row is
        a deterministic recovery identity and must be adopted rather than ignored.
        """

        conn = self.database._require_conn()
        clean = str(scan_id or "").strip()
        if clean:
            row = conn.execute(
                "SELECT status FROM discovery_scans WHERE scan_id=?",
                (clean,),
            ).fetchone()
            if row is not None and str(row[0]) in {"running", "ambiguous"}:
                return clean

        rows = conn.execute(
            """SELECT scan_id FROM discovery_scans
               WHERE status IN ('running','ambiguous')
                 AND scan_id LIKE 'autorenew-scan:%'
               ORDER BY id DESC LIMIT 2"""
        ).fetchall()
        if len(rows) > 1:
            raise V2DatabaseError(
                "Multiple unresolved asteroid autorenew discovery scans require manual reconciliation"
            )
        return str(rows[0][0]) if rows else None

    def record_scan_observations(
        self,
        *,
        scan_id: str,
        sequence_index: int,
        observation_ids: Sequence[int],
    ) -> None:
        ids = tuple(dict.fromkeys(int(value) for value in observation_ids if int(value) > 0))
        if not ids:
            return
        if not 0 <= int(sequence_index) < 120:
            raise V2DatabaseError(f"Invalid autorenew discovery sequence index: {sequence_index}")
        now = _now()
        conn = self.database._require_conn()
        with conn:
            conn.executemany(
                """INSERT OR IGNORE INTO asteroid_autorenew_scan_observations(
                    scan_id,sequence_index,observation_id,created_at
                ) VALUES(?,?,?,?)""",
                [(str(scan_id), int(sequence_index), value, now) for value in ids],
            )

    def scan_observation_ids(self, scan_id: str) -> tuple[int, ...]:
        rows = self.database._require_conn().execute(
            """SELECT observation_id FROM asteroid_autorenew_scan_observations
               WHERE scan_id=? ORDER BY sequence_index, observation_id""",
            (str(scan_id),),
        ).fetchall()
        return tuple(int(row[0]) for row in rows)

    def disarm_on_startup(self) -> AsteroidAutorenewState:
        current = self.read()
        if not current.armed:
            return current
        unresolved_scan_id = self._unresolved_active_scan_id(current.active_scan_id)
        conn = self.database._require_conn()
        detail = "Persisted armed state was disarmed on process startup; explicit Start required"
        if unresolved_scan_id:
            detail += f"; unresolved discovery scan preserved: {unresolved_scan_id}"
        with conn:
            conn.execute(
                """UPDATE asteroid_autorenew_state
                   SET armed=0,status='disarmed_restart',next_cycle_at=NULL,
                       active_scan_id=?, detail=?, updated_at=? WHERE singleton_id=1""",
                (unresolved_scan_id, detail, _now()),
            )
        return self.read()

    def arm(
        self,
        *,
        session_id: str,
        source_planet_id: str,
        source_coord: str,
        account_fingerprint: str,
        recycler_count: int,
        max_flights: int,
        safety_seconds: int,
        buffer_minutes: int,
    ) -> AsteroidAutorenewState:
        if not str(session_id).strip():
            raise V2DatabaseError("Asteroid autorenew session_id is required")
        if int(recycler_count) <= 0 or int(max_flights) <= 0:
            raise V2DatabaseError("Recycler count and max flights must be positive")
        if int(safety_seconds) < 0 or int(buffer_minutes) < 0:
            raise V2DatabaseError("Safety seconds and buffer minutes must be non-negative")
        current = self.read()
        if current.armed:
            raise V2DatabaseError("Asteroid autorenew is already armed")
        unresolved_scan_id = self._unresolved_active_scan_id(current.active_scan_id)
        if unresolved_scan_id:
            raise V2DatabaseError(
                "Asteroid autorenew blocked by unresolved discovery scan "
                f"{unresolved_scan_id}; reconcile it before a new Start"
            )
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE asteroid_autorenew_state
                   SET status='armed_due',armed=1,session_id=?,source_planet_id=?,source_coord=?,
                       account_fingerprint=?,recycler_count=?,max_flights=?,safety_seconds=?,
                       buffer_minutes=?,next_cycle_at=NULL,active_scan_id=NULL,
                       cycle_started_at=NULL,last_return_at=NULL,verified_sent=0,detail='',updated_at=?
                   WHERE singleton_id=1""",
                (
                    str(session_id), str(source_planet_id), str(source_coord),
                    str(account_fingerprint), int(recycler_count), int(max_flights),
                    int(safety_seconds), int(buffer_minutes), _now(),
                ),
            )
        return self.read()

    def transition(
        self,
        *,
        status: str,
        armed: bool | None = None,
        next_cycle_at: str | None = None,
        active_scan_id: str | None = None,
        cycle_started_at: str | None = None,
        last_return_at: str | None = None,
        verified_sent: int | None = None,
        detail: str = "",
    ) -> AsteroidAutorenewState:
        if status not in ASTEROID_AUTORENEW_STATUSES:
            raise V2DatabaseError(f"Invalid asteroid autorenew status: {status}")
        current = self.read()
        values = {
            "status": status,
            "armed": int(current.armed if armed is None else bool(armed)),
            "next_cycle_at": next_cycle_at,
            "active_scan_id": active_scan_id,
            "cycle_started_at": cycle_started_at,
            "last_return_at": last_return_at,
            "verified_sent": current.verified_sent if verified_sent is None else max(0, int(verified_sent)),
            "detail": str(detail or ""),
            "updated_at": _now(),
        }
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE asteroid_autorenew_state
                   SET status=:status,armed=:armed,next_cycle_at=:next_cycle_at,
                       active_scan_id=:active_scan_id,cycle_started_at=:cycle_started_at,
                       last_return_at=:last_return_at,verified_sent=:verified_sent,
                       detail=:detail,updated_at=:updated_at WHERE singleton_id=1""",
                values,
            )
        return self.read()

    def stop(self, *, status: str, detail: str) -> AsteroidAutorenewState:
        if status not in {
            "disarmed",
            "stopped_manual",
            "stopped_no_asteroids",
            "stopped_capacity",
            "stopped_insufficient",
            "stopped_captcha",
            "stopped_ambiguous",
            "blocked",
        }:
            raise V2DatabaseError(f"Invalid asteroid autorenew stop status: {status}")
        current = self.read()
        unresolved_scan_id = self._unresolved_active_scan_id(current.active_scan_id)
        stop_detail = str(detail or "")
        if unresolved_scan_id and unresolved_scan_id not in stop_detail:
            stop_detail = (
                f"{stop_detail}; unresolved discovery scan preserved: {unresolved_scan_id}"
                if stop_detail
                else f"Unresolved discovery scan preserved: {unresolved_scan_id}"
            )
        return self.transition(
            status=status,
            armed=False,
            next_cycle_at=None,
            active_scan_id=unresolved_scan_id,
            detail=stop_detail,
        )
