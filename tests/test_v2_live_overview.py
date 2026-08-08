from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.flight_source import ActiveFlightSnapshot, FleetCapacitySnapshot, FlightSourceStatus


SCHEMA = """
CREATE TABLE targets (coord TEXT PRIMARY KEY);
CREATE TABLE history (id INTEGER PRIMARY KEY);
CREATE TABLE queue (id INTEGER PRIMARY KEY);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Source:
    def __init__(self) -> None:
        self.status_reads = 0
        self.refreshes = 0

    def status(self):
        self.status_reads += 1
        return FlightSourceStatus(True, "fixture live")

    def refresh(self):
        self.refreshes += 1

    def flights(self):
        return (
            ActiveFlightSnapshot("3:39:11", "3:1:2", "Атака", return_at="2026-08-08T12:00:00+00:00"),
            ActiveFlightSnapshot("3:39:11", "3:1:3", "Переработка", return_at="2026-08-08T12:10:00+00:00"),
            ActiveFlightSnapshot("3:39:11", "2:5:6", "Атака", return_at="2026-08-08T12:20:00+00:00"),
        )

    def owned_planets(self):
        return ("3:39:11",)

    def capacity(self):
        return FleetCapacitySnapshot(used=20, maximum=22, free=2, source="fixture")


def create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?)",
            (
                ("home_g", "3"), ("home_s", "39"), ("home_p", "11"),
                ("farm_return_buffer_minutes", "5"),
                ("farm_next_cycle_at", "2026-08-08T12:03:00+00:00"),
            ),
        )


def test_overview_never_probes_before_explicit_refresh_and_uses_cached_facts(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    create_db(db)
    before = db.read_bytes()
    source = Source()
    context = V2ApplicationContext(db, flight_source=source)
    try:
        initial = context.live_overview_snapshot()
        assert initial.checked is False
        assert source.status_reads == 0
        assert source.refreshes == 0

        status = context.refresh_live_source()
        assert status.available is True
        assert source.status_reads == 1
        assert source.refreshes == 1

        snapshot = context.live_overview_snapshot()
        assert source.status_reads == 1, "cached Overview must not probe browser again"
        assert snapshot.active_count == 3
        assert snapshot.personal_outgoing_count == 2  # command target is excluded
        assert snapshot.excluded_count == 1
        assert snapshot.farm_blocking_count == 1
        assert snapshot.capacity is not None
        assert (snapshot.capacity.used, snapshot.capacity.maximum, snapshot.capacity.free) == (20, 22, 2)
        assert snapshot.latest_farm_return_at == "2026-08-08T12:00:00+00:00"
        assert snapshot.inferred_farm_ready_at == "2026-08-08T12:05:00+00:00"
        assert snapshot.persisted_farm_ready_at == "2026-08-08T12:03:00+00:00"
        assert snapshot.effective_farm_ready_at == "2026-08-08T12:05:00+00:00"
    finally:
        context.close()
    assert db.read_bytes() == before


def test_overview_ui_requires_user_action_for_live_probe() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "ui" / "pages" / "overview.py").read_text(encoding="utf-8")
    constructor = source.split("    def refresh_live(self)", 1)[0]
    assert "context.refresh_live_source()" not in constructor
    assert "self.live_refresh_button.clicked.connect(self.refresh_live)" in source
    assert "self.context.refresh_live_source()" in source
    assert "live_overview_snapshot()" in source
    for forbidden in ("send_raid", "prepare_raid", "request_spy", "delete_messages", "BrowserWorker"):
        assert forbidden not in source
