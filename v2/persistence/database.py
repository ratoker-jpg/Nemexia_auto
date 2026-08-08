from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


V2_SCHEMA_VERSION = 2


class V2DatabaseError(RuntimeError):
    pass


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _preflight_existing_schema(path: Path) -> None:
    """Reject unsupported existing files before any writable SQLite pragma runs."""
    if not path.exists():
        return
    try:
        with sqlite3.connect(_readonly_uri(path), uri=True) as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        raise V2DatabaseError(f"Cannot open existing V2 database read-only: {path}") from exc
    if current > V2_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"V2 database schema {current} is newer than supported {V2_SCHEMA_VERSION}"
        )


class V2Database:
    """Own the isolated V2 SQLite database and its schema migrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        _preflight_existing_schema(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            self._migrate()
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            self._conn.close()
            raise

    def __enter__(self) -> "V2Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        return self._conn

    def schema_version(self) -> int:
        return int(self._require_conn().execute("PRAGMA user_version").fetchone()[0])

    def integrity_check(self) -> str:
        return str(self._require_conn().execute("PRAGMA integrity_check").fetchone()[0])

    def backup_to(self, destination: Path) -> Path:
        """Create a consistent SQLite snapshot, including committed WAL content."""
        conn = self._require_conn()
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_conn = sqlite3.connect(target)
        try:
            conn.backup(backup_conn)
            backup_conn.commit()
        finally:
            backup_conn.close()
        return target

    def table_names(self) -> frozenset[str]:
        rows = self._require_conn().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return frozenset(str(row[0]) for row in rows)

    def read_setting_raw(self, key: str) -> str | None:
        row = self._require_conn().execute("SELECT value FROM settings WHERE key=?", (str(key),)).fetchone()
        return str(row[0]) if row is not None else None

    def write_setting_raw(self, key: str, value: str) -> None:
        self.write_settings_raw({str(key): str(value)})

    def write_settings_raw(self, values: Mapping[str, str]) -> None:
        """Commit one validated settings batch atomically."""
        conn = self._require_conn()
        if not values:
            return
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = [(str(key), str(value), now) for key, value in values.items()]
        with conn:
            conn.executemany(
                """
                INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                rows,
            )

    def read_all_settings_raw(self) -> dict[str, str]:
        rows = self._require_conn().execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def begin_raid_action(
        self,
        *,
        request_id: str,
        source: str,
        target: str,
        player: str,
        ship_count: int,
    ) -> None:
        """Persist intent before any SendFleet side effect; request_id is immutable/idempotent."""
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO raid_actions(
                        request_id, source, target, player, ship_count, status,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (str(request_id), str(source), str(target), str(player), int(ship_count), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(f"Raid request already exists: {request_id}") from exc

    def finish_raid_action(
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
        allowed = {"verified", "ambiguous", "rejected", "failed"}
        if status not in allowed:
            raise V2DatabaseError(f"Invalid raid action status: {status}")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                """
                UPDATE raid_actions
                   SET status=?, fleet_id=?, sent_at=?, arrival_at=?, return_at=?,
                       detail=?, updated_at=?
                 WHERE request_id=? AND status='pending'
                """,
                (
                    status, fleet_id, sent_at, arrival_at, return_at,
                    str(detail or ""), now, str(request_id),
                ),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending raid request not found: {request_id}")

    def read_raid_action(self, request_id: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            "SELECT * FROM raid_actions WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_raid_actions(self, *, limit: int = 200) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            "SELECT * FROM raid_actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def unresolved_raid_action(self, *, source: str, target: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            """
            SELECT * FROM raid_actions
             WHERE source=? AND target=? AND status IN ('pending','ambiguous')
             ORDER BY id DESC LIMIT 1
            """,
            (str(source), str(target)),
        ).fetchone()
        return dict(row) if row is not None else None

    def _migrate(self) -> None:
        current = self.schema_version()
        if current > V2_SCHEMA_VERSION:
            raise V2DatabaseError(
                f"V2 database schema {current} is newer than supported {V2_SCHEMA_VERSION}"
            )
        while current < V2_SCHEMA_VERSION:
            next_version = current + 1
            migration = getattr(self, f"_migrate_to_{next_version}", None)
            if not callable(migration):
                raise V2DatabaseError(f"Missing V2 migration {current} -> {next_version}")
            with self._require_conn():
                migration()
                self._require_conn().execute(f"PRAGMA user_version={next_version}")
            current = next_version

    def _record_migration(self, version: int) -> None:
        self._require_conn().execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (int(version), datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
        )

    def _migrate_to_1(self) -> None:
        self._require_conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )
        self._record_migration(1)

    def _migrate_to_2(self) -> None:
        self._require_conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS raid_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                player TEXT NOT NULL,
                ship_count INTEGER NOT NULL CHECK(ship_count > 0),
                status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','rejected','failed')),
                fleet_id TEXT,
                sent_at TEXT,
                arrival_at TEXT,
                return_at TEXT,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_raid_actions_target_status
                ON raid_actions(source, target, status);
            """
        )
        self._record_migration(2)
