from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.context import V2ApplicationContext


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


def test_plan_reflects_persisted_queue_without_mutation(tmp_path: Path) -> None:
    db = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO targets VALUES ('3:1:2','Alpha',1,3,1,2,1,0,'',700000,800000,12,'2026-08-08T09:00:00+00:00',0,NULL,NULL)")
        conn.execute("INSERT INTO targets VALUES ('3:1:3','Beta',1,3,1,3,0,1,'',100,200,3,NULL,0,NULL,NULL)")
        conn.execute("INSERT INTO queue VALUES (1,'3:1:3',2,'sent')")
        conn.execute("INSERT INTO queue VALUES (2,'3:1:2',1,'queued')")
    before = db.read_bytes()

    context = V2ApplicationContext(db)
    try:
        plan = context.plan()
        assert [item.coord for item in plan] == ['3:1:2', '3:1:3']
        assert plan[0].position == 1
        assert plan[0].minerals == 800000
        assert plan[1].state == 'sent'
        assert plan[1].blacklisted is True
    finally:
        context.close()
    assert db.read_bytes() == before


def test_plan_ui_is_non_actionable() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / 'v2' / 'ui' / 'pages' / 'plan.py').read_text(encoding='utf-8')
    main = (root / 'v2' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
    assert 'context.plan()' in page
    assert 'PlanPage(self.context' in main
    for forbidden in ('send_raid', 'prepare_raid', 'replace_queue', 'generate_queue', 'BrowserWorker', 'UPDATE ', 'DELETE ', 'INSERT INTO'):
        assert forbidden not in page
