from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from v2.persistence.database import V2Database, V2DatabaseError


AUTOMATIC_RECON_SCHEMA_VERSION = 1
_UNRESOLVED = ("pending", "ambiguous")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def install_automatic_recon_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS automatic_recon_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    row = conn.execute(
        "SELECT COALESCE(MAX(version),0) FROM automatic_recon_schema_migrations"
    ).fetchone()
    current = int(row[0]) if row else 0
    if current > AUTOMATIC_RECON_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"Automatic recon schema {current} is newer than supported "
            f"{AUTOMATIC_RECON_SCHEMA_VERSION}"
        )
    if current < 1:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS automatic_recon_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','failed_safe')),
                fleet_id TEXT NOT NULL,
                source_coord TEXT NOT NULL,
                target_coord TEXT NOT NULL,
                account_fingerprint TEXT NOT NULL,
                planet_id TEXT NOT NULL,
                baseline_json TEXT NOT NULL,
                after_json TEXT,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_automatic_recon_status
                ON automatic_recon_actions(status, id DESC);
            """
        )
        conn.execute(
            "INSERT INTO automatic_recon_schema_migrations(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )


@dataclass(frozen=True)
class AutomaticReconJournalRecord:
    request_id: str
    status: str
    fleet_id: str
    source_coord: str
    target_coord: str
    account_fingerprint: str
    planet_id: str
    baseline_keys: tuple[str, ...]
    after_keys: tuple[str, ...] | None
    detail: str
    created_at: str
    updated_at: str


class AutomaticReconConflictError(RuntimeError):
    pass


class AutomaticReconJournalRepository:
    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_automatic_recon_schema(conn)

    @staticmethod
    def _record(row: sqlite3.Row | None) -> AutomaticReconJournalRecord | None:
        if row is None:
            return None
        return AutomaticReconJournalRecord(
            request_id=str(row["request_id"]),
            status=str(row["status"]),
            fleet_id=str(row["fleet_id"]),
            source_coord=str(row["source_coord"]),
            target_coord=str(row["target_coord"]),
            account_fingerprint=str(row["account_fingerprint"]),
            planet_id=str(row["planet_id"]),
            baseline_keys=tuple(json.loads(str(row["baseline_json"] or "[]"))),
            after_keys=(
                tuple(json.loads(str(row["after_json"])))
                if row["after_json"] is not None else None
            ),
            detail=str(row["detail"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def unresolved(self) -> tuple[AutomaticReconJournalRecord, ...]:
        rows = self.database._require_conn().execute(
            """SELECT * FROM automatic_recon_actions
               WHERE status IN ('pending','ambiguous') ORDER BY id DESC"""
        ).fetchall()
        return tuple(record for row in rows if (record := self._record(row)) is not None)

    def begin(
        self,
        *,
        request_id: str,
        fleet_id: str,
        source_coord: str,
        target_coord: str,
        account_fingerprint: str,
        planet_id: str,
        baseline_keys: tuple[str, ...],
    ) -> AutomaticReconJournalRecord:
        request_id = str(request_id).strip()
        if not request_id:
            raise V2DatabaseError("Automatic recon request_id is required")
        unresolved = self.unresolved()
        if unresolved:
            raise AutomaticReconConflictError(
                f"Automatic recon has unresolved request: {unresolved[0].request_id} ({unresolved[0].status})"
            )
        conn = self.database._require_conn()
        now = _now()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO automatic_recon_actions(
                        request_id,status,fleet_id,source_coord,target_coord,
                        account_fingerprint,planet_id,baseline_json,created_at,updated_at
                    ) VALUES(?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request_id,
                        str(fleet_id),
                        str(source_coord),
                        str(target_coord),
                        str(account_fingerprint),
                        str(planet_id),
                        json.dumps(sorted(set(baseline_keys)), ensure_ascii=False),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(f"Automatic recon request already exists: {request_id}") from exc
        record = self.read(request_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Automatic recon request was not persisted: {request_id}")
        return record

    def finish(
        self,
        request_id: str,
        *,
        status: str,
        after_keys: tuple[str, ...] | None,
        detail: str,
    ) -> AutomaticReconJournalRecord:
        if status not in {"verified", "ambiguous", "failed_safe"}:
            raise V2DatabaseError(f"Invalid automatic recon terminal status: {status}")
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE automatic_recon_actions
                   SET status=?, after_json=?, detail=?, updated_at=?
                 WHERE request_id=? AND status='pending'""",
                (
                    status,
                    (
                        json.dumps(sorted(set(after_keys)), ensure_ascii=False)
                        if after_keys is not None else None
                    ),
                    str(detail or ""),
                    _now(),
                    str(request_id),
                ),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending automatic recon request not found: {request_id}")
        record = self.read(request_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Automatic recon request disappeared: {request_id}")
        return record

    def read(self, request_id: str) -> AutomaticReconJournalRecord | None:
        row = self.database._require_conn().execute(
            "SELECT * FROM automatic_recon_actions WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        return self._record(row)

    def recent(self, *, limit: int = 200) -> tuple[AutomaticReconJournalRecord, ...]:
        rows = self.database._require_conn().execute(
            "SELECT * FROM automatic_recon_actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return tuple(record for row in rows if (record := self._record(row)) is not None)
