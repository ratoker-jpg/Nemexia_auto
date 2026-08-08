from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


V2_SCHEMA_VERSION = 1


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

    def schema_version(self) -> int:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def integrity_check(self) -> str:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        return str(self._conn.execute("PRAGMA integrity_check").fetchone()[0])

    def table_names(self) -> frozenset[str]:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        rows = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return frozenset(str(row[0]) for row in rows)

    def read_setting_raw(self, key: str) -> str | None:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (str(key),)).fetchone()
        return str(row[0]) if row is not None else None

    def write_setting_raw(self, key: str, value: str) -> None:
        self.write_settings_raw({str(key): str(value)})

    def write_settings_raw(self, values: Mapping[str, str]) -> None:
        """Commit one validated settings batch atomically."""
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        if not values:
            return
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = [(str(key), str(value), now) for key, value in values.items()]
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                rows,
            )

    def read_all_settings_raw(self) -> dict[str, str]:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        rows = self._conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

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
            with self._conn:
                migration()
                self._conn.execute(f"PRAGMA user_version={next_version}")
            current = next_version

    def _migrate_to_1(self) -> None:
        self._conn.executescript(
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
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (1, datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
        )
