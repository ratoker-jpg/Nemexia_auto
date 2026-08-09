from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from v2.persistence.database import V2Database, V2DatabaseError


REST_MODE_SCHEMA_VERSION = 1
REST_MODE_ATTACK_UNVERIFIED = "UNVERIFIED_DATA_REQUIRED"
REST_MODE_STATUSES = frozenset(
    {
        "DISARMED",
        "STARTING",
        "WATCHING",
        "ACTIVITY_WARNING",
        "BLOCKED_BROWSER",
        "BLOCKED_IDENTITY",
        "BLOCKED_BUSY",
        "BLOCKED_AMBIGUOUS",
        "CAPTCHA_REQUIRED",
        "ERROR",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def install_rest_mode_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS rest_mode_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    row = conn.execute(
        "SELECT COALESCE(MAX(version),0) FROM rest_mode_schema_migrations"
    ).fetchone()
    current = int(row[0]) if row else 0
    if current > REST_MODE_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"Rest Mode schema {current} is newer than supported {REST_MODE_SCHEMA_VERSION}"
        )
    if current < 1:
        conn.executescript(
            f"""CREATE TABLE IF NOT EXISTS rest_mode_state (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                armed INTEGER NOT NULL CHECK(armed IN (0,1)),
                status TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                server_host TEXT NOT NULL DEFAULT '',
                account_fingerprint TEXT NOT NULL DEFAULT '',
                planet_id TEXT NOT NULL DEFAULT '',
                planet_coord TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                last_success_at TEXT,
                next_check_at TEXT,
                last_activity_minutes INTEGER,
                activity_epoch INTEGER NOT NULL DEFAULT 0 CHECK(activity_epoch >= 0),
                activity_warning_sent INTEGER NOT NULL DEFAULT 0 CHECK(activity_warning_sent IN (0,1)),
                attack_watch_state TEXT NOT NULL DEFAULT '{REST_MODE_ATTACK_UNVERIFIED}',
                last_error TEXT NOT NULL DEFAULT '',
                blocking_navigation_request_id TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );"""
        )
        conn.execute(
            """INSERT OR IGNORE INTO rest_mode_state(
                singleton_id,armed,status,attack_watch_state,updated_at
            ) VALUES(1,0,'DISARMED',?,?)""",
            (REST_MODE_ATTACK_UNVERIFIED, _now()),
        )
        conn.execute(
            "INSERT INTO rest_mode_schema_migrations(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )


@dataclass(frozen=True)
class RestModeState:
    armed: bool
    status: str
    session_id: str
    server_host: str
    account_fingerprint: str
    planet_id: str
    planet_coord: str
    started_at: str | None
    last_success_at: str | None
    next_check_at: str | None
    last_activity_minutes: int | None
    activity_epoch: int
    activity_warning_sent: bool
    attack_watch_state: str
    last_error: str
    blocking_navigation_request_id: str
    detail: str
    updated_at: str

    @property
    def due_at(self) -> datetime | None:
        if not self.next_check_at:
            return None
        parsed = datetime.fromisoformat(self.next_check_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class RestModeRepository:
    """Component-versioned Rest Mode state; persisted armed state is never startup authority."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_rest_mode_schema(conn)

    @staticmethod
    def _state(row: sqlite3.Row) -> RestModeState:
        status = str(row["status"])
        if status not in REST_MODE_STATUSES:
            raise V2DatabaseError(f"Invalid persisted Rest Mode status: {status}")
        return RestModeState(
            armed=bool(row["armed"]),
            status=status,
            session_id=str(row["session_id"] or ""),
            server_host=str(row["server_host"] or ""),
            account_fingerprint=str(row["account_fingerprint"] or ""),
            planet_id=str(row["planet_id"] or ""),
            planet_coord=str(row["planet_coord"] or ""),
            started_at=str(row["started_at"]) if row["started_at"] else None,
            last_success_at=str(row["last_success_at"]) if row["last_success_at"] else None,
            next_check_at=str(row["next_check_at"]) if row["next_check_at"] else None,
            last_activity_minutes=(
                int(row["last_activity_minutes"])
                if row["last_activity_minutes"] is not None
                else None
            ),
            activity_epoch=int(row["activity_epoch"]),
            activity_warning_sent=bool(row["activity_warning_sent"]),
            attack_watch_state=str(row["attack_watch_state"] or REST_MODE_ATTACK_UNVERIFIED),
            last_error=str(row["last_error"] or ""),
            blocking_navigation_request_id=str(row["blocking_navigation_request_id"] or ""),
            detail=str(row["detail"] or ""),
            updated_at=str(row["updated_at"]),
        )

    def read(self) -> RestModeState:
        row = self.database._require_conn().execute(
            "SELECT * FROM rest_mode_state WHERE singleton_id=1"
        ).fetchone()
        if row is None:  # pragma: no cover
            raise V2DatabaseError("Rest Mode singleton state is missing")
        return self._state(row)

    def disarm_on_startup(self) -> RestModeState:
        state = self.read()
        if not state.armed and state.status == "DISARMED":
            return state
        conn = self.database._require_conn()
        detail = state.detail
        if state.armed:
            detail = "Previous process ended while Rest Mode was armed; explicit Start required"
        with conn:
            conn.execute(
                """UPDATE rest_mode_state
                   SET armed=0,status='DISARMED',next_check_at=NULL,detail=?,updated_at=?
                   WHERE singleton_id=1""",
                (detail, _now()),
            )
        return self.read()

    def begin_start(
        self,
        *,
        session_id: str,
        server_host: str,
        account_fingerprint: str,
        planet_id: str,
        planet_coord: str,
        started_at: str,
    ) -> RestModeState:
        previous = self.read()
        same_identity = (
            previous.server_host == str(server_host)
            and previous.account_fingerprint == str(account_fingerprint)
            and previous.planet_id == str(planet_id)
            and previous.planet_coord == str(planet_coord)
        )
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE rest_mode_state SET
                    armed=0,status='STARTING',session_id=?,server_host=?,account_fingerprint=?,
                    planet_id=?,planet_coord=?,started_at=?,next_check_at=NULL,
                    activity_epoch=?,activity_warning_sent=?,attack_watch_state=?,
                    last_error='',blocking_navigation_request_id='',detail='',updated_at=?
                   WHERE singleton_id=1""",
                (
                    str(session_id),
                    str(server_host),
                    str(account_fingerprint),
                    str(planet_id),
                    str(planet_coord),
                    str(started_at),
                    previous.activity_epoch if same_identity else 0,
                    1 if (same_identity and previous.activity_warning_sent) else 0,
                    REST_MODE_ATTACK_UNVERIFIED,
                    _now(),
                ),
            )
        return self.read()

    def save_observation(
        self,
        *,
        status: str,
        armed: bool,
        activity_minutes: int,
        activity_epoch: int,
        warning_sent: bool,
        observed_at: str,
        next_check_at: str | None,
        detail: str = "",
    ) -> RestModeState:
        if status not in {"WATCHING", "ACTIVITY_WARNING"}:
            raise V2DatabaseError(f"Observation cannot use Rest Mode status: {status}")
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE rest_mode_state SET
                    armed=?,status=?,last_success_at=?,next_check_at=?,last_activity_minutes=?,
                    activity_epoch=?,activity_warning_sent=?,attack_watch_state=?,last_error='',
                    blocking_navigation_request_id='',detail=?,updated_at=?
                   WHERE singleton_id=1""",
                (
                    1 if armed else 0,
                    status,
                    str(observed_at),
                    next_check_at,
                    max(0, int(activity_minutes)),
                    max(0, int(activity_epoch)),
                    1 if warning_sent else 0,
                    REST_MODE_ATTACK_UNVERIFIED,
                    str(detail or ""),
                    _now(),
                ),
            )
        return self.read()

    def block(
        self,
        *,
        status: str,
        detail: str,
        blocking_navigation_request_id: str = "",
    ) -> RestModeState:
        if status not in {
            "BLOCKED_BROWSER",
            "BLOCKED_IDENTITY",
            "BLOCKED_BUSY",
            "BLOCKED_AMBIGUOUS",
            "CAPTCHA_REQUIRED",
            "ERROR",
        }:
            raise V2DatabaseError(f"Invalid Rest Mode block status: {status}")
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE rest_mode_state SET
                    armed=0,status=?,next_check_at=NULL,last_error=?,
                    blocking_navigation_request_id=?,detail=?,updated_at=?
                   WHERE singleton_id=1""",
                (
                    str(status),
                    str(detail or ""),
                    str(blocking_navigation_request_id or ""),
                    str(detail or ""),
                    _now(),
                ),
            )
        return self.read()

    def stop(self, *, detail: str = "Stopped by operator") -> RestModeState:
        conn = self.database._require_conn()
        with conn:
            conn.execute(
                """UPDATE rest_mode_state SET
                    armed=0,status='DISARMED',next_check_at=NULL,detail=?,updated_at=?
                   WHERE singleton_id=1""",
                (str(detail or ""), _now()),
            )
        return self.read()
