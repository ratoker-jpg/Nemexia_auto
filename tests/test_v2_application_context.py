from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.context import V2ApplicationContext, legacy_db_path


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


def make_valid_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO targets VALUES ('3:1:2','Alpha',1,3,1,2,1,0,'',NULL,600000,NULL,'2026-08-08T07:00:00+00:00',0,NULL,NULL)"
        )


def test_legacy_path_detection_does_not_create_directories(tmp_path: Path) -> None:
    local = tmp_path / "Local"
    path = legacy_db_path(environ={"LOCALAPPDATA": str(local)}, home=tmp_path)
    assert path == local / "NemexiaRaidManager" / "nemexia.sqlite3"
    assert not local.exists()


def test_missing_legacy_db_yields_empty_safe_context(tmp_path: Path) -> None:
    source = tmp_path / "missing" / "nemexia.sqlite3"
    context = V2ApplicationContext(source)
    try:
        status = context.status()
        assert status.available is False
        assert status.mode == "read-only"
        assert context.overview().targets_total == 0
        assert context.targets() == []
        assert context.history() == []
        assert not source.exists()
    finally:
        context.close()


def test_auto_detect_override_reads_existing_db_without_mutation(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy.sqlite3"
    make_valid_db(source)
    before = source.read_bytes()
    monkeypatch.setenv("NEMEXIA_V2_READ_DB", str(source))

    context = V2ApplicationContext.auto_detect()
    try:
        status = context.status()
        assert status.available is True
        assert status.mode == "read-only"
        assert "query_only=1" in status.detail
        assert context.overview().targets_total == 1
        assert context.targets()[0].minerals == 600000
    finally:
        context.close()

    assert source.read_bytes() == before
