from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from v2.application.read_store import ReadOnlyStore, ReadStoreUnavailable


SCHEMA = """
CREATE TABLE targets (
    coord TEXT PRIMARY KEY, player TEXT, energy INTEGER, g INTEGER, s INTEGER, p INTEGER,
    enabled INTEGER, blacklisted INTEGER, notes TEXT, metal INTEGER, minerals INTEGER,
    resource_gas INTEGER, last_spy_at TEXT, raid_count INTEGER, last_raid_at TEXT,
    last_return_at TEXT
);
CREATE TABLE history (
    id INTEGER PRIMARY KEY, source TEXT, target TEXT, player TEXT, ship_count INTEGER,
    sent_at TEXT, arrival_at TEXT, return_at TEXT, status TEXT, error TEXT
);
CREATE TABLE queue (id INTEGER PRIMARY KEY, coord TEXT, position INTEGER, state TEXT);
"""


def build_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO targets VALUES
            ('3:1:2', 'Alpha', 9000, 3, 1, 2, 1, 0, '', 700000, 800000, 12,
             '2026-08-08T07:00:00+00:00', 4, '2026-08-08T06:00:00+00:00', NULL),
            ('3:2:3', 'Beta', 1000, 3, 2, 3, 0, 1, 'blocked', NULL, 100, NULL,
             NULL, 0, NULL, NULL)
            """
        )
        conn.execute(
            "INSERT INTO queue VALUES (1, '3:1:2', 1, 'queued')"
        )
        conn.execute(
            """
            INSERT INTO history VALUES
            (1, '3:39:11', '3:1:2', 'Alpha', 25,
             '2026-08-08T06:00:00+00:00', NULL, NULL, 'sent', NULL)
            """
        )


def test_store_reads_real_schema_without_writes(tmp_path: Path) -> None:
    db = tmp_path / "nemexia.sqlite3"
    build_db(db)

    with ReadOnlyStore(db) as store:
        status = store.status()
        assert status.query_only is True
        assert {'targets', 'history', 'queue'} <= status.tables

        overview = store.overview()
        assert overview.targets_total == 2
        assert overview.targets_enabled == 1
        assert overview.queue_queued == 1
        assert overview.history_total == 1
        assert overview.latest_spy_at == '2026-08-08T07:00:00+00:00'

        targets = store.list_targets()
        assert [item.coord for item in targets] == ['3:1:2', '3:2:3']
        assert targets[0].minerals == 800000
        assert targets[0].gas == 12

        history = store.list_history()
        assert len(history) == 1
        assert history[0].target == '3:1:2'
        assert history[0].ship_count == 25

        with pytest.raises(sqlite3.OperationalError):
            store._conn.execute("UPDATE targets SET player='changed'")

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT player FROM targets WHERE coord='3:1:2'").fetchone()[0] == 'Alpha'


def test_missing_file_fails_without_creating_it(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite3"
    with pytest.raises(ReadStoreUnavailable):
        ReadOnlyStore(db)
    assert not db.exists()


def test_missing_required_tables_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "bad.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE targets(coord TEXT PRIMARY KEY)")

    with pytest.raises(ReadStoreUnavailable, match="Required tables are missing"):
        ReadOnlyStore(db)
