from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.flight_source import ActiveFlightSnapshot, FlightSourceStatus
from v2.domain.flights import FlightDirection


SCHEMA = """
CREATE TABLE targets (coord TEXT PRIMARY KEY);
CREATE TABLE history (id INTEGER PRIMARY KEY);
CREATE TABLE queue (id INTEGER PRIMARY KEY);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Source:
    def status(self):
        return FlightSourceStatus(True, "fixture")

    def flights(self):
        return (
            ActiveFlightSnapshot("3:39:11", "3:1:2", "Атака", return_at="2026-08-08T12:00:00+00:00"),
            ActiveFlightSnapshot("3:39:8", "3:1:3", "Атака", return_at="2026-08-08T12:10:00+00:00"),
            ActiveFlightSnapshot("3:39:11", "2:5:6", "Атака", return_at="2026-08-08T12:20:00+00:00"),
        )

    def owned_planets(self):
        return ("3:39:11", "3:39:8")

    def capacity(self):
        return None


def create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?)",
            (("home_g", "3"), ("home_s", "39"), ("home_p", "11")),
        )


def test_context_combines_readonly_settings_owned_planets_and_command_exclusion(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    create_db(db)
    before = db.read_bytes()
    context = V2ApplicationContext(db, flight_source=Source())
    try:
        items = context.classified_active_flights()
        assert len(items) == 3
        assert items[0].facts.direction is FlightDirection.OUTGOING
        assert items[0].facts.blocks_farm_cycle is True
        assert items[1].facts.direction is FlightDirection.OUTGOING
        assert items[1].facts.blocks_farm_cycle is False
        assert items[2].facts.excluded is True
        assert items[2].facts.blocks_farm_cycle is False
        assert len(context.farm_blocking_flights()) == 1
    finally:
        context.close()
    assert db.read_bytes() == before
