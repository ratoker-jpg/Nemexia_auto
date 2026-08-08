from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Mapping, Sequence

from v2.persistence.database import V2Database, V2DatabaseError


def install_debris_candidate_schema(conn: sqlite3.Connection) -> None:
    """Install append-only V2-owned debris evidence storage.

    This table is feature-local and additive: it never reads or mutates legacy
    SQLite and never replaces evidence from systems that are not currently open.
    """

    conn.executescript(
        """CREATE TABLE IF NOT EXISTS debris_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            galaxy INTEGER NOT NULL CHECK(galaxy BETWEEN 1 AND 3),
            system INTEGER NOT NULL CHECK(system BETWEEN 1 AND 40),
            position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 24),
            last_move_at TEXT NOT NULL,
            next_move_at TEXT NOT NULL,
            period_seconds INTEGER NOT NULL CHECK(period_seconds > 0),
            observed_at TEXT NOT NULL,
            evidence_source TEXT NOT NULL,
            marker TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            UNIQUE(
                galaxy, system, position,
                last_move_at, next_move_at, period_seconds,
                observed_at, evidence_source, marker
            )
        );
        CREATE INDEX IF NOT EXISTS idx_debris_observations_observed
            ON debris_observations(observed_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_debris_observations_origin
            ON debris_observations(galaxy, system, position, observed_at DESC);"""
    )


class DebrisObservationRepository:
    """Persist immutable marker-positive debris observations in V2 storage."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_debris_candidate_schema(conn)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def canonical_iso(value: object) -> str:
        text = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise V2DatabaseError(f"Invalid debris observation timestamp: {value!r}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @classmethod
    def canonical_row(cls, row: Mapping[str, object]) -> tuple[object, ...]:
        galaxy = int(row["galaxy"])
        system = int(row["system"])
        position = int(row["position"])
        period = int(row["period_seconds"])
        source = str(row.get("evidence_source") or "galaxy.squareInfo").strip()
        marker = str(row.get("marker") or "").strip()
        if galaxy not in {1, 2, 3}:
            raise V2DatabaseError(f"Unsupported debris galaxy: {galaxy}")
        if not 1 <= system <= 40:
            raise V2DatabaseError(f"Invalid debris system: {system}")
        if not 1 <= position <= 24:
            raise V2DatabaseError(f"Invalid debris position: {position}")
        if period <= 0 or not source or not marker:
            raise V2DatabaseError("Debris observation provenance is incomplete")
        last_move = cls.canonical_iso(row["last_move_at"])
        next_move = cls.canonical_iso(row["next_move_at"])
        observed = cls.canonical_iso(row["observed_at"])
        if datetime.fromisoformat(next_move) <= datetime.fromisoformat(last_move):
            raise V2DatabaseError("Debris next_move_at must be after last_move_at")
        return galaxy, system, position, last_move, next_move, period, observed, source, marker

    def insert(self, rows: Sequence[Mapping[str, object]]) -> int:
        if not rows:
            return 0
        canonical = [self.canonical_row(row) for row in rows]
        ingested_at = self._now()
        conn = self.database._require_conn()
        with conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO debris_observations(
                    galaxy, system, position,
                    last_move_at, next_move_at, period_seconds,
                    observed_at, evidence_source, marker, ingested_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [tuple(row) + (ingested_at,) for row in canonical],
            )
            return conn.total_changes - before

    def list(self, *, limit: int | None = None) -> list[dict[str, object]]:
        conn = self.database._require_conn()
        sql = """SELECT id, galaxy, system, position,
                        last_move_at, next_move_at, period_seconds,
                        observed_at, evidence_source, marker, ingested_at
                   FROM debris_observations
                  ORDER BY observed_at DESC, id DESC"""
        rows = conn.execute(sql).fetchall() if limit is None else conn.execute(
            sql + " LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def identities(self) -> frozenset[tuple[object, ...]]:
        rows = self.database._require_conn().execute(
            """SELECT galaxy, system, position,
                      last_move_at, next_move_at, period_seconds,
                      observed_at, evidence_source, marker
                 FROM debris_observations"""
        ).fetchall()
        return frozenset(tuple(row) for row in rows)
