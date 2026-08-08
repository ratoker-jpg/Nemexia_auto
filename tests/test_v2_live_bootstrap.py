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


def test_v2_preferred_port_wins_after_environment_overrides(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    create_settings_fixture(db, port=9333)
    before = db.read_bytes()
    preferred = resolve_cdp_endpoint(db, environ={}, preferred_port=9444)
    assert preferred.endpoint == "http://127.0.0.1:9444"
    assert preferred.source == "V2 settings: cdp_port"
    env = resolve_cdp_endpoint(db, environ={"NEMEXIA_V2_CDP_PORT": "9555"}, preferred_port=9444)
    assert env.endpoint == "http://127.0.0.1:9555"
    assert db.read_bytes() == before


def test_endpoint_override_wins_and_missing_db_falls_back(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    override = resolve_cdp_endpoint(missing, environ={"NEMEXIA_V2_CDP_ENDPOINT": "http://127.0.0.1:9444/"})
    assert override.endpoint == "http://127.0.0.1:9444"
    assert resolve_cdp_endpoint(missing, environ={}).endpoint == "http://127.0.0.1:9222"


def test_context_close_propagates_to_browser_source(tmp_path: Path) -> None:
    class Backend:
        def __init__(self): self.closed = False
        def status(self): return BrowserReadStatus(False, detail="offline")
        def flights(self): return ()
        def capacity(self): return None
        def close(self): self.closed = True
    backend = Backend()
    context = V2ApplicationContext(tmp_path / "missing.sqlite3", flight_source=V2BrowserFlightSource(backend))
    context.close()
    assert backend.closed is True


def test_qt_bootstrap_wires_isolated_settings_spy_recon_and_asteroid_context() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app_qt.py").read_text(encoding="utf-8")
    asteroid_context = (root / "v2/application/asteroid_context.py").read_text(encoding="utf-8")
    assert "V2Database(paths.database)" in source
    assert "V2SettingsRepository(database)" in source
    assert "LegacySettingsImporter" in source
    assert 'preferred_port=settings.get("cdp_port")' in source
    assert "V2SpyCdpBackend" in source
    assert "SpyActionService" in source
    assert "V2ReconRepository(database)" in source
    assert "recon.import_legacy_targets(legacy)" in source
    assert "AsteroidEnabledApplicationContext(" in source
    assert "class AsteroidEnabledApplicationContext(ReconOwnedApplicationContext)" in asteroid_context
    assert "V2BrowserFlightSource" in source and "V2BrowserReportSource" in source
    assert "report_source=report_source" in source and "spy_actions=spy_actions" in source
    assert "v2_recon=recon" in source
    for forbidden in ("BrowserWorker", "launch_yandex", "delete_messages", "app_entry.py"):
        assert forbidden not in source
