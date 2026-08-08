from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from v2.persistence.database import V2Database, V2DatabaseError


ASTEROID_ACTION_STATUSES = frozenset({"pending", "verified", "ambiguous", "failed_safe"})
_FLEET_ID_RE = re.compile(r"^[1-9]\d*$")


def install_asteroid_journal_schema(conn: sqlite3.Connection) -> None:
    """Install schema v7 asteroid action journal inside the V2-owned database."""

    conn.executescript(
        """CREATE TABLE IF NOT EXISTS asteroid_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            observation_coord TEXT NOT NULL,
            observation_last_move_at TEXT NOT NULL,
            observation_next_move_at TEXT NOT NULL,
            observation_period_seconds INTEGER NOT NULL CHECK(observation_period_seconds > 0),
            observation_observed_at TEXT NOT NULL,
            target TEXT NOT NULL,
            recycler_count INTEGER NOT NULL CHECK(recycler_count > 0),
            safety_seconds INTEGER NOT NULL CHECK(safety_seconds >= 0),
            prepared_at TEXT NOT NULL,
            one_way_seconds INTEGER NOT NULL CHECK(one_way_seconds > 0),
            round_trip_seconds INTEGER NOT NULL CHECK(round_trip_seconds > 0),
            shifts INTEGER NOT NULL CHECK(shifts >= 0),
            gas_needed INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','failed_safe')),
            fleet_id TEXT,
            sent_at TEXT,
            arrival_at TEXT,
            return_at TEXT,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_asteroid_actions_status
            ON asteroid_actions(status, id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_asteroid_actions_unresolved_identity
            ON asteroid_actions(source, observation_coord, observation_next_move_at, target)
            WHERE status IN ('pending','ambiguous');"""
    )


class AsteroidJournalRepository:
    """V2-owned persistent identity and recovery state for asteroid dispatches."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _canonical_iso(value: str) -> str:
        text = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise V2DatabaseError(f"Invalid asteroid journal timestamp: {value!r}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _positive_fleet_id(value: object) -> str:
        fleet_id = str(value or "").strip()
        if _FLEET_ID_RE.fullmatch(fleet_id) is None:
            raise V2DatabaseError("fleet_id must be a positive integer identity")
        return fleet_id

    def begin(
        self,
        *,
        request_id: str,
        source: str,
        observation_coord: str,
        observation_last_move_at: str,
        observation_next_move_at: str,
        observation_period_seconds: int,
        observation_observed_at: str,
        target: str,
        recycler_count: int,
        safety_seconds: int,
        prepared_at: str,
        one_way_seconds: int,
        round_trip_seconds: int,
        shifts: int,
        gas_needed: int | None,
    ) -> None:
        conn = self.database._require_conn()
        now = self._now()
        last_move = self._canonical_iso(observation_last_move_at)
        next_move = self._canonical_iso(observation_next_move_at)
        observed_at = self._canonical_iso(observation_observed_at)
        prepared = self._canonical_iso(prepared_at)
        try:
            with conn:
                conn.execute(
                    """INSERT INTO asteroid_actions(
                        request_id, source, observation_coord,
                        observation_last_move_at, observation_next_move_at,
                        observation_period_seconds, observation_observed_at,
                        target, recycler_count, safety_seconds, prepared_at,
                        one_way_seconds, round_trip_seconds, shifts, gas_needed,
                        status, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
                    (
                        str(request_id), str(source), str(observation_coord),
                        last_move, next_move,
                        int(observation_period_seconds), observed_at,
                        str(target), int(recycler_count), int(safety_seconds), prepared,
                        int(one_way_seconds), int(round_trip_seconds), int(shifts), gas_needed,
                        now, now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(
                "Asteroid request conflicts with an existing request or unresolved trajectory: "
                f"{request_id}"
            ) from exc

    def finish(
        self,
        request_id: str,
        *,
        status: str,
        fleet_id: str | None = None,
        sent_at: str | None = None,
        arrival_at: str | None = None,
        return_at: str | None = None,
        detail: str = "",
    ) -> None:
        if status not in {"verified", "ambiguous", "failed_safe"}:
            raise V2DatabaseError(f"Invalid asteroid action status: {status}")
        if status == "verified":
            fleet_id = self._positive_fleet_id(fleet_id)
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE asteroid_actions
                   SET status=?, fleet_id=?, sent_at=?, arrival_at=?, return_at=?, detail=?, updated_at=?
                 WHERE request_id=? AND status='pending'""",
                (
                    status, fleet_id, sent_at, arrival_at, return_at,
                    str(detail or ""), self._now(), str(request_id),
                ),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending asteroid request not found: {request_id}")

    def resolve_verified(
        self,
        request_id: str,
        *,
        fleet_id: str,
        sent_at: str | None = None,
        arrival_at: str | None = None,
        return_at: str | None = None,
        detail: str = "live-flight reconciliation",
    ) -> None:
        fleet_id = self._positive_fleet_id(fleet_id)
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE asteroid_actions
                   SET status='verified', fleet_id=?,
                       sent_at=COALESCE(sent_at, ?),
                       arrival_at=COALESCE(arrival_at, ?),
                       return_at=COALESCE(return_at, ?),
                       detail=?, updated_at=?
                 WHERE request_id=? AND status IN ('pending','ambiguous')""",
                (
                    fleet_id, sent_at, arrival_at, return_at,
                    str(detail or ""), self._now(), str(request_id),
                ),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Unresolved asteroid request not found: {request_id}")

    def read(self, request_id: str) -> dict[str, object] | None:
        row = self.database._require_conn().execute(
            "SELECT * FROM asteroid_actions WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def list(self, *, limit: int = 200) -> list[dict[str, object]]:
        rows = self.database._require_conn().execute(
            "SELECT * FROM asteroid_actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def unresolved(
        self,
        *,
        source: str,
        observation_coord: str,
        observation_next_move_at: str,
        target: str,
    ) -> dict[str, object] | None:
        next_move = self._canonical_iso(observation_next_move_at)
        row = self.database._require_conn().execute(
            """SELECT * FROM asteroid_actions
                WHERE source=? AND observation_coord=?
                  AND observation_next_move_at=? AND target=?
                  AND status IN ('pending','ambiguous')
                ORDER BY id DESC LIMIT 1""",
            (
                str(source), str(observation_coord),
                next_move, str(target),
            ),
        ).fetchone()
        return dict(row) if row is not None else None
