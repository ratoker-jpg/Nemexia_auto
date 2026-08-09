from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from v2.persistence.database import V2Database, V2DatabaseError


ASTEROID_AUTORENEW_SCHEMA_VERSION = 1
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
    """Component-versioned V2-owned scheduler state.

    `armed` is persisted only for crash diagnostics. Service construction always
    calls `disarm_on_startup()`, so persisted armed state can never authorize a
    new browser mutation in a later process.
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

    def disarm_on_startup(self) -> AsteroidAutorenewState:
        current = self.read()
        if not current.armed:
            return current
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE asteroid_autorenew_state
                   SET armed=0,status='disarmed_restart',next_cycle_at=NULL,
                       active_scan_id=NULL,
                       detail='Persisted armed state was disarmed on process startup; explicit Start required',
                       updated_at=? WHERE singleton_id=1""",
                (_now(),),
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
        return self.transition(
            status=status,
            armed=False,
            next_cycle_at=None,
            active_scan_id=None,
            detail=detail,
        )
