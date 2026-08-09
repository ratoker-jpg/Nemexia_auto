from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from v2.persistence.database import V2Database, V2DatabaseError


NAVIGATION_JOURNAL_SCHEMA_VERSION = 1
NAVIGATION_STATUSES = frozenset({"pending", "verified", "ambiguous", "failed_safe"})
NAVIGATION_ACTION_KINDS = frozenset({
    "bind_session",
    "switch_planet",
    "prepare_fleets",
    "prepare_messages",
    "prepare_galaxy",
    "galaxy_system",
})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_json(value: Mapping[str, object] | None) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def install_navigation_journal_schema(conn: sqlite3.Connection) -> None:
    """Install component-versioned navigation journal in the V2-owned database.

    Core V2 schema remains independently versioned by PRAGMA user_version. This
    component has its own explicit migration ledger so AUTO-03 does not require a
    navigation mutation merely to open/upgrade an existing V2 database.
    """

    conn.execute(
        """CREATE TABLE IF NOT EXISTS navigation_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )"""
    )
    row = conn.execute("SELECT COALESCE(MAX(version),0) FROM navigation_schema_migrations").fetchone()
    current = int(row[0]) if row is not None else 0
    if current > NAVIGATION_JOURNAL_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"Navigation journal schema {current} is newer than supported "
            f"{NAVIGATION_JOURNAL_SCHEMA_VERSION}"
        )
    if current < 1:
        conn.executescript(
            """CREATE TABLE IF NOT EXISTS navigation_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                action_kind TEXT NOT NULL CHECK(action_kind IN (
                    'bind_session','switch_planet','prepare_fleets',
                    'prepare_messages','prepare_galaxy','galaxy_system'
                )),
                status TEXT NOT NULL CHECK(status IN (
                    'pending','verified','ambiguous','failed_safe'
                )),
                before_json TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                after_json TEXT,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_navigation_actions_status
                ON navigation_actions(status, id DESC);
            CREATE INDEX IF NOT EXISTS idx_navigation_actions_kind_status
                ON navigation_actions(action_kind, status, id DESC);
            """
        )
        conn.execute(
            "INSERT INTO navigation_schema_migrations(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )


@dataclass(frozen=True)
class NavigationJournalRecord:
    request_id: str
    action_kind: str
    status: str
    before: dict[str, object]
    intent: dict[str, object]
    after: dict[str, object] | None
    detail: str
    created_at: str
    updated_at: str


class NavigationJournalRepository:
    """Persistent exactly-one request ledger for browser context mutations."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        conn = database._require_conn()
        with conn:
            install_navigation_journal_schema(conn)

    @staticmethod
    def _record(row: sqlite3.Row | None) -> NavigationJournalRecord | None:
        if row is None:
            return None
        return NavigationJournalRecord(
            request_id=str(row["request_id"]),
            action_kind=str(row["action_kind"]),
            status=str(row["status"]),
            before=json.loads(str(row["before_json"] or "{}")),
            intent=json.loads(str(row["intent_json"] or "{}")),
            after=json.loads(str(row["after_json"])) if row["after_json"] else None,
            detail=str(row["detail"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def begin(
        self,
        *,
        request_id: str,
        action_kind: str,
        before: Mapping[str, object],
        intent: Mapping[str, object],
    ) -> NavigationJournalRecord:
        request_id = str(request_id).strip()
        action_kind = str(action_kind).strip()
        if not request_id:
            raise V2DatabaseError("Navigation request_id is required")
        if action_kind not in NAVIGATION_ACTION_KINDS:
            raise V2DatabaseError(f"Invalid navigation action kind: {action_kind}")
        conn = self.database._require_conn()
        now = _now()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO navigation_actions(
                        request_id, action_kind, status,
                        before_json, intent_json, created_at, updated_at
                    ) VALUES(?, ?, 'pending', ?, ?, ?, ?)""",
                    (
                        request_id,
                        action_kind,
                        _canonical_json(before),
                        _canonical_json(intent),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(f"Navigation request already exists: {request_id}") from exc
        record = self.read(request_id)
        if record is None:  # pragma: no cover - defensive SQLite invariant
            raise V2DatabaseError(f"Navigation request was not persisted: {request_id}")
        return record

    def finish(
        self,
        request_id: str,
        *,
        status: str,
        after: Mapping[str, object] | None = None,
        detail: str = "",
    ) -> NavigationJournalRecord:
        if status not in {"verified", "ambiguous", "failed_safe"}:
            raise V2DatabaseError(f"Invalid navigation terminal status: {status}")
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE navigation_actions
                   SET status=?, after_json=?, detail=?, updated_at=?
                 WHERE request_id=? AND status='pending'""",
                (
                    status,
                    _canonical_json(after) if after is not None else None,
                    str(detail or ""),
                    _now(),
                    str(request_id),
                ),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending navigation request not found: {request_id}")
        record = self.read(request_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Navigation request disappeared: {request_id}")
        return record

    def reconcile_verified(
        self,
        request_id: str,
        *,
        after: Mapping[str, object],
        detail: str = "read-only context reconciliation",
    ) -> NavigationJournalRecord:
        conn = self.database._require_conn()
        with conn:
            cursor = conn.execute(
                """UPDATE navigation_actions
                   SET status='verified', after_json=?, detail=?, updated_at=?
                 WHERE request_id=? AND status IN ('pending','ambiguous')""",
                (_canonical_json(after), str(detail or ""), _now(), str(request_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Unresolved navigation request not found: {request_id}")
        record = self.read(request_id)
        if record is None:  # pragma: no cover
            raise V2DatabaseError(f"Navigation request disappeared: {request_id}")
        return record

    def read(self, request_id: str) -> NavigationJournalRecord | None:
        row = self.database._require_conn().execute(
            "SELECT * FROM navigation_actions WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        return self._record(row)

    def recent(self, *, limit: int = 200) -> tuple[NavigationJournalRecord, ...]:
        rows = self.database._require_conn().execute(
            "SELECT * FROM navigation_actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return tuple(record for row in rows if (record := self._record(row)) is not None)

    def unresolved(self, *, limit: int = 200) -> tuple[NavigationJournalRecord, ...]:
        rows = self.database._require_conn().execute(
            """SELECT * FROM navigation_actions
                WHERE status IN ('pending','ambiguous')
                ORDER BY id DESC LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return tuple(record for row in rows if (record := self._record(row)) is not None)
