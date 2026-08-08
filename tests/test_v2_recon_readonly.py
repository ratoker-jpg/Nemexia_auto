from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.read_store import ReadOnlyStore


BASE_SCHEMA = """
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

SPY_SCHEMA = """
CREATE TABLE spy_reports (
    id INTEGER PRIMARY KEY, message_id TEXT, dedupe_key TEXT UNIQUE, target_coord TEXT,
    report_at TEXT, energy INTEGER, metal INTEGER, minerals INTEGER, gas INTEGER,
    population INTEGER, ships INTEGER, defense INTEGER, completeness TEXT,
    source TEXT, imported_at TEXT, raw_payload TEXT
);
"""


def test_recon_reads_persisted_spy_reports_newest_first_without_mutation(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(BASE_SCHEMA + SPY_SCHEMA)
        conn.execute(
            "INSERT INTO spy_reports VALUES (1,'m1','d1','3:1:2','2026-08-08T08:00:00+00:00',"
            "9000,700000,800000,12,100,5,6,'full','messages','2026-08-08T08:01:00+00:00','{}')"
        )
        conn.execute(
            "INSERT INTO spy_reports VALUES (2,'m2','d2','3:1:3','2026-08-08T09:00:00+00:00',"
            "8000,600000,900000,9,80,3,4,'resources','messages','2026-08-08T09:01:00+00:00','{}')"
        )
    before = db.read_bytes()

    context = V2ApplicationContext(db)
    try:
        reports = context.recon()
        assert [item.target_coord for item in reports] == ['3:1:3', '3:1:2']
        assert reports[0].minerals == 900000
        assert reports[1].ships == 5
    finally:
        context.close()
    assert db.read_bytes() == before


def test_old_database_without_spy_reports_stays_readable(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(BASE_SCHEMA)
    with ReadOnlyStore(db) as store:
        assert store.list_recon() == []


def test_recon_ui_has_no_refresh_or_game_actions() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / 'v2' / 'ui' / 'pages' / 'recon.py').read_text(encoding='utf-8')
    main = (root / 'v2' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
    assert 'context.recon()' in page
    assert 'ReconPage(self.context' in main
    for forbidden in ('BrowserWorker', 'request_spy', 'delete_messages', 'send_raid', 'INSERT INTO', 'UPDATE '):
        assert forbidden not in page
