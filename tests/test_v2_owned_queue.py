import sqlite3
from pathlib import Path

from v2.application.read_store import ReadOnlyStore
from v2.application.v2_queue import V2QueueRepository
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION


LEGACY_SCHEMA = """
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


def create_legacy(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO targets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("3:1:2", "Alpha", 0, 3, 1, 2, 1, 0, "", 10, 20, 30,
             "2026-08-08T10:00:00+00:00", 0, None, None),
        )
        conn.execute("INSERT INTO queue VALUES (1,'3:1:2',1,'queued')")


def test_queue_import_is_one_time_and_legacy_remains_byte_identical(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.sqlite3"
    create_legacy(legacy_path)
    before = legacy_path.read_bytes()
    with V2Database(tmp_path / "v2.sqlite3") as db:
        assert db.schema_version() == V2_SCHEMA_VERSION == 5
        queue = V2QueueRepository(db)
        with ReadOnlyStore(legacy_path) as legacy:
            assert queue.import_legacy_if_empty(legacy) == 1
            assert queue.import_legacy_if_empty(legacy) == 0
        rows = queue.list()
        assert len(rows) == 1
        assert rows[0].coord == "3:1:2"
        assert rows[0].player == "Alpha"
        assert rows[0].state == "queued"
        assert (rows[0].metal, rows[0].minerals, rows[0].gas) == (10, 20, 30)
        queue.set_state(rows[0].id, "sending")
        assert queue.list()[0].state == "sending"
    assert legacy_path.read_bytes() == before


def test_existing_v2_queue_is_never_overwritten_by_legacy_import(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.sqlite3"
    create_legacy(legacy_path)
    with V2Database(tmp_path / "v2.sqlite3") as db:
        queue = V2QueueRepository(db)
        with ReadOnlyStore(legacy_path) as legacy:
            queue.import_legacy_if_empty(legacy)
        first = queue.list()[0]
        queue.set_state(first.id, "sent")
        with ReadOnlyStore(legacy_path) as legacy:
            assert queue.import_legacy_if_empty(legacy) == 0
        assert queue.list()[0].state == "sent"
