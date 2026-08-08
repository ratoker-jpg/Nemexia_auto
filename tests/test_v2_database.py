from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from v2.persistence.database import V2Database, V2DatabaseError, V2_SCHEMA_VERSION


def test_new_v2_database_is_versioned_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "v2" / "nemexia.sqlite3"
    assert not path.exists()
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION
        assert {"settings", "schema_migrations", "raid_actions", "raid_queue", "spy_actions"}.issubset(
            db.table_names()
        )
        assert db.integrity_check() == "ok"
    assert path.is_file()

    with V2Database(path) as reopened:
        assert reopened.schema_version() == V2_SCHEMA_VERSION
        assert reopened.integrity_check() == "ok"


def test_schema_v1_is_migrated_without_losing_settings(tmp_path: Path) -> None:
    path = tmp_path / "schema-v1.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO settings(key, value, updated_at)
            VALUES('cdp_port', '9333', '2026-08-08T10:00:00+00:00');
            INSERT INTO schema_migrations(version, applied_at)
            VALUES(1, '2026-08-08T10:00:00+00:00');
            PRAGMA user_version=1;
            """
        )
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION
        assert db.read_setting_raw("cdp_port") == "9333"
        assert {"raid_actions", "raid_queue", "spy_actions"}.issubset(db.table_names())
        assert db.integrity_check() == "ok"
        migrations = db._require_conn().execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [int(row[0]) for row in migrations] == [1, 2, 3, 4]


def test_future_schema_is_rejected_instead_of_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=99")
    before = path.read_bytes()
    with pytest.raises(V2DatabaseError, match="newer than supported"):
        V2Database(path)
    assert path.read_bytes() == before


def test_v2_database_never_targets_legacy_path_by_convention() -> None:
    root = Path(__file__).resolve().parents[1]
    persistence = (root / "v2" / "persistence" / "database.py").read_text(encoding="utf-8")
    assert "NemexiaRaidManager" not in persistence
    assert "legacy_db_path" not in persistence
    assert "ReadOnlyStore" not in persistence
