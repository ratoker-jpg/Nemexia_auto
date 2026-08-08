from __future__ import annotations

from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.flight_source import FlightSourceStatus


class RefreshableSource:
    def __init__(self) -> None:
        self.refreshes = 0
        self.status_reads = 0

    def status(self) -> FlightSourceStatus:
        self.status_reads += 1
        return FlightSourceStatus(True, "fixture connected")

    def flights(self):
        return ()

    def capacity(self):
        return None

    def refresh(self) -> None:
        self.refreshes += 1


def test_live_source_is_not_probed_until_explicit_refresh(tmp_path: Path) -> None:
    source = RefreshableSource()
    context = V2ApplicationContext(tmp_path / "missing.sqlite3", flight_source=source)
    try:
        assert context.cached_flight_status() is None
        assert source.status_reads == 0
        status = context.refresh_live_source()
        assert status.available is True
        assert source.refreshes == 1
        assert source.status_reads == 1
        assert context.cached_flight_status() == status
    finally:
        context.close()


def test_active_refresh_replaces_rows_but_keeps_table_read_only() -> None:
    root = Path(__file__).resolve().parents[1]
    active = (root / "v2" / "ui" / "pages" / "active.py").read_text(encoding="utf-8")
    tables = (root / "v2" / "ui" / "pages" / "read_tables.py").read_text(encoding="utf-8")
    main = (root / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "def reload_view" in active
    assert "refresh_live_source()" in active
    assert "self.model.replace_rows(rows)" in active
    assert "def replace_rows" in tables
    assert "beginResetModel()" in tables
    assert "NoEditTriggers" in tables
    assert 'getattr(page, "reload_view", None)' in main

    combined = active + tables
    for forbidden in (
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "UPDATE ",
        "INSERT INTO",
        "DELETE FROM",
    ):
        assert forbidden not in combined
