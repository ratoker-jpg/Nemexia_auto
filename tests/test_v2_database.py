from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from v2.persistence.database import V2Database, V2DatabaseError, V2_SCHEMA_VERSION


def test_new_v2_database_is_versioned_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "v2" / "nemexia.sqlite3"
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION == 7
        assert {
            "settings", "schema_migrations", "raid_actions", "raid_queue", "spy_actions",
            "recon_targets", "recon_reports", "asteroid_actions",
        }.issubset(db.table_names())
        assert db.integrity_check() == "ok"
    with V2Database(path) as reopened:
        assert reopened.schema_version() == 7 and reopened.integrity_check() == "ok"


def test_schema_v1_is_migrated_without_losing_settings(tmp_path: Path) -> None:
    path = tmp_path / "schema-v1.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
        INSERT INTO settings VALUES('cdp_port','9333','2026-08-08T10:00:00+00:00');
        INSERT INTO schema_migrations VALUES(1,'2026-08-08T10:00:00+00:00');
        PRAGMA user_version=1;
        """)
    with V2Database(path) as db:
        assert db.schema_version() == 7
        assert db.read_setting_raw("cdp_port") == "9333"
        assert db.integrity_check() == "ok"
        versions = db._require_conn().execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert [int(row[0]) for row in versions] == [1, 2, 3, 4, 5, 6, 7]


def _create_schema_v4_spy_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_migrations VALUES(4,'2026-08-08T10:00:00+00:00');
        CREATE TABLE spy_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL, target TEXT NOT NULL,
            probe_count INTEGER NOT NULL CHECK(probe_count > 0), probe_ship_key TEXT NOT NULL,
            available_probes INTEGER NOT NULL CHECK(available_probes >= 0),
            status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','failed_safe')),
            report_id TEXT, requested_at TEXT, report_at TEXT, detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_spy_actions_target_status ON spy_actions(source, target, status);
        CREATE UNIQUE INDEX idx_spy_actions_unresolved_target
            ON spy_actions(source, target) WHERE status IN ('pending','ambiguous');
        INSERT INTO spy_actions(request_id,source,target,probe_count,probe_ship_key,available_probes,status,detail,created_at,updated_at)
        VALUES('old','3:39:11','2:22:19',5,'spy_probe',20,'ambiguous','','2026-08-08T10:00:00+00:00','2026-08-08T10:00:00+00:00');
        PRAGMA user_version=4;
        """)


def test_schema_v4_spy_rows_are_preserved_without_invented_fleet_identity(tmp_path: Path) -> None:
    path = tmp_path / "schema-v4.sqlite3"
    _create_schema_v4_spy_database(path)
    with V2Database(path) as migrated:
        row = migrated.read_spy_action("old")
        assert row is not None and row["fleet_id"] is None
        assert row["status"] == "ambiguous"
        assert "fleet_id was not recorded" in str(row["detail"])
        assert migrated.schema_version() == 7
        assert {"recon_targets", "recon_reports", "asteroid_actions"}.issubset(migrated.table_names())


def test_schema_v5_rebuild_rolls_back_as_one_transaction(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "schema-v4-interrupted.sqlite3"
    _create_schema_v4_spy_database(path)
    original = V2Database._record_migration

    def interrupt_after_rebuild(self: V2Database, version: int) -> None:
        if version == 5:
            raise RuntimeError("simulated interruption before version commit")
        original(self, version)

    monkeypatch.setattr(V2Database, "_record_migration", interrupt_after_rebuild)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        V2Database(path)

    with sqlite3.connect(path) as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 4
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(spy_actions)").fetchall()}
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "probe_count" in columns
        assert "fleet_id" not in columns
        assert "spy_actions_v4" not in tables
        assert conn.execute("SELECT request_id FROM spy_actions").fetchone()[0] == "old"


def test_future_schema_is_rejected_instead_of_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=99")
    before = path.read_bytes()
    with pytest.raises(V2DatabaseError, match="newer than supported"):
        V2Database(path)
    assert path.read_bytes() == before


def test_v2_database_never_targets_legacy_path_by_convention() -> None:
    source = (Path(__file__).resolve().parents[1] / "v2/persistence/database.py").read_text(encoding="utf-8")
    assert "NemexiaRaidManager" not in source
    assert "legacy_db_path" not in source
    assert "ReadOnlyStore" not in source
