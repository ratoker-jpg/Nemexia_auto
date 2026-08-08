from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.browser_read_service import BrowserReadStatus, V2BrowserFlightSource
from v2.application.context import V2ApplicationContext
from v2.application.live_bootstrap import resolve_cdp_endpoint


SCHEMA = """
CREATE TABLE targets (coord TEXT PRIMARY KEY);
CREATE TABLE history (id INTEGER PRIMARY KEY);
CREATE TABLE queue (id INTEGER PRIMARY KEY);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def create_settings_fixture(path: Path, *, port: int) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO settings(key,value) VALUES('port',?)", (str(port),))


def test_endpoint_uses_legacy_port_without_mutating_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    create_settings_fixture(db, port=9333)
    before = db.read_bytes()
    config = resolve_cdp_endpoint(db, environ={})
    assert config.endpoint == "http://127.0.0.1:9333"
    assert config.source == "legacy SQLite setting: port"
    assert db.read_bytes() == before


def test_endpoint_override_wins_and_missing_db_falls_back(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    override = resolve_cdp_endpoint(
        missing,
        environ={"NEMEXIA_V2_CDP_ENDPOINT": "http://127.0.0.1:9444/"},
    )
    assert override.endpoint == "http://127.0.0.1:9444"
    fallback = resolve_cdp_endpoint(missing, environ={})
    assert fallback.endpoint == "http://127.0.0.1:9222"


def test_context_close_propagates_to_browser_source(tmp_path: Path) -> None:
    class Backend:
        def __init__(self) -> None:
            self.closed = False

        def status(self) -> BrowserReadStatus:
            return BrowserReadStatus(False, detail="offline")

        def flights(self):
            return ()

        def capacity(self):
            return None

        def close(self) -> None:
            self.closed = True

    backend = Backend()
    context = V2ApplicationContext(
        tmp_path / "missing.sqlite3",
        flight_source=V2BrowserFlightSource(backend),
    )
    context.close()
    assert backend.closed is True


def test_qt_bootstrap_wires_only_read_side_browser_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app_qt.py").read_text(encoding="utf-8")
    assert "ReadOnlyCdpBackend" in source
    assert "V2BrowserFlightSource" in source
    assert "resolve_cdp_endpoint" in source
    for forbidden in (
        "BrowserWorker",
        "launch_yandex",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "app_entry.py",
    ):
        assert forbidden not in source
