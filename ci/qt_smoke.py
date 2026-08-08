from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from v2.application.context import V2ApplicationContext
from v2.application.flight_source import ActiveFlightSnapshot, FleetCapacitySnapshot, FlightSourceStatus
from v2.application.legacy_settings_import import LegacySettingsImporter
from v2.application.read_store import ReadOnlyStore
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database
from v2.runtime_paths import build_runtime_paths, ensure_runtime_paths
from v2.ui.main_window import MainWindow
from v2.ui.theme import ORBITAL_COMMAND_QSS


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
CREATE TABLE spy_reports (
    id INTEGER PRIMARY KEY, message_id TEXT, dedupe_key TEXT UNIQUE, target_coord TEXT,
    report_at TEXT, energy INTEGER, metal INTEGER, minerals INTEGER, gas INTEGER,
    population INTEGER, ships INTEGER, defense INTEGER, completeness TEXT,
    source TEXT, imported_at TEXT, raw_payload TEXT
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class FakeLiveFlightSource:
    def __init__(self) -> None:
        self.refreshes = 0
        self.status_reads = 0
        self.closed = False

    def refresh(self) -> None:
        self.refreshes += 1

    def status(self) -> FlightSourceStatus:
        self.status_reads += 1
        return FlightSourceStatus(True, "fixture CDP read-only · fleets.php")

    def flights(self):
        return (
            ActiveFlightSnapshot("3:39:11", "3:1:2", "Атака", return_at="2026-08-08T09:20:00+00:00", fleet_id="77"),
            ActiveFlightSnapshot("3:39:8", "3:5:4", "Переработка", return_at="2026-08-08T09:25:00+00:00", fleet_id="78"),
        )

    def owned_planets(self):
        return ("3:39:11", "3:39:8")

    def capacity(self) -> FleetCapacitySnapshot:
        return FleetCapacitySnapshot(20, 22, 2, "fixture game DOM #FleetsCount/#MaxFleets")

    def close(self) -> None:
        self.closed = True


def create_fixture(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO targets VALUES ('3:1:2','Alpha',9000,3,1,2,1,0,'',700000,800000,12,'2026-08-08T07:00:00+00:00',4,'2026-08-08T06:00:00+00:00',NULL)")
        conn.execute("INSERT INTO queue VALUES (1,'3:1:2',1,'queued')")
        conn.execute("INSERT INTO history VALUES (1,'3:39:11','3:1:2','Alpha',25,'2026-08-08T06:00:00+00:00',NULL,'2026-08-08T08:00:00+00:00','sent',NULL)")
        conn.execute("INSERT INTO spy_reports VALUES (1,'m1','d1','3:1:2','2026-08-08T07:00:00+00:00',9000,700000,800000,12,100,5,6,'full','messages','2026-08-08T07:01:00+00:00','{}')")
        conn.executemany("INSERT INTO settings(key,value) VALUES(?,?)", (("port","9333"),("home_g","3"),("home_s","39"),("home_p","11"),("farm_return_buffer_minutes","7")))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nemexia_qt_smoke_", ignore_cleanup_errors=True) as temp:
        root = Path(temp)
        legacy_db = root / "legacy.sqlite3"
        create_fixture(legacy_db)
        before = legacy_db.read_bytes()
        paths = ensure_runtime_paths(build_runtime_paths(env={"LOCALAPPDATA": str(root / "local")}, platform_name="nt", home=root))

        database = V2Database(paths.database)
        settings = V2SettingsRepository(database)
        with ReadOnlyStore(legacy_db) as source:
            LegacySettingsImporter(source, settings).import_missing()
        assert settings.get("cdp_port") == 9333
        assert settings.get("farm_home") == "3:39:11"
        assert settings.get("farm_return_buffer_minutes") == 7

        live_source = FakeLiveFlightSource()
        context = V2ApplicationContext(legacy_db, flight_source=live_source, v2_settings=settings, v2_database=database)
        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(ORBITAL_COMMAND_QSS)
        window = MainWindow(paths, context)
        try:
            assert window.minimumWidth() == 1180 and window.minimumHeight() == 720
            assert window.stack.count() == 11
            expected = {"overview":"OverviewPage","plan":"PlanPage","active":"ActivePage","recon":"ReconPage","targets":"TargetsPage","history":"HistoryPage","settings":"SettingsPage","diagnostics":"DiagnosticsPage"}
            for key, class_name in expected.items():
                page = window.stack.widget(window._page_index[key])
                assert page.__class__.__name__ == class_name, (key, page.__class__.__name__)

            active = window.stack.widget(window._page_index["active"])
            settings_page = window.stack.widget(window._page_index["settings"])
            diagnostics = window.stack.widget(window._page_index["diagnostics"])
            assert live_source.status_reads == 0 and live_source.refreshes == 0
            window._show_page("active", "Активные", "Текущие полёты и возвраты")
            app.processEvents()
            assert live_source.refreshes == 1 and live_source.status_reads == 1
            assert active.model.rowCount() == 2
            assert active.capacity is not None and active.capacity.free == 2

            window._show_page("settings", "Настройки", "Параметры приложения")
            settings_page.return_buffer.setValue(9)
            settings_page.save_settings()
            assert context.v2_setting("farm_return_buffer_minutes") == 9

            window._show_page("diagnostics", "Диагностика", "Логи и техническое состояние")
            app.processEvents()
            assert live_source.status_reads == 1
            assert diagnostics.live_status_value.text() == "Доступны"
            window.show(); app.processEvents()
        finally:
            window.close(); app.processEvents(); context.close()

        assert live_source.closed is True
        assert legacy_db.read_bytes() == before
        assert paths.database.is_file()
        with V2Database(paths.database) as check:
            assert check.integrity_check() == "ok"
            assert V2SettingsRepository(check).get("farm_return_buffer_minutes") == 9

    print("OK: PySide6 V2 settings/runtime offscreen smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
