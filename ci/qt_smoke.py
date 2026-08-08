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
from v2.application.flight_source import (
    ActiveFlightSnapshot,
    FleetCapacitySnapshot,
    FlightSourceStatus,
)
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
"""


class FakeLiveFlightSource:
    """Network-free fixture for the complete Qt live-read presentation path."""

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
            ActiveFlightSnapshot(
                source="3:39:11",
                target="3:1:2",
                mission="Атака",
                departure_at="2026-08-08T09:00:00+00:00",
                arrival_at="2026-08-08T09:10:00+00:00",
                return_at="2026-08-08T09:20:00+00:00",
                fleet_id="77",
            ),
            ActiveFlightSnapshot(
                source="3:39:8",
                target="3:5:4",
                mission="Переработка",
                return_at="2026-08-08T09:25:00+00:00",
                fleet_id="78",
            ),
        )

    def capacity(self) -> FleetCapacitySnapshot:
        return FleetCapacitySnapshot(
            used=20,
            maximum=22,
            free=2,
            source="fixture game DOM #FleetsCount/#MaxFleets",
        )

    def close(self) -> None:
        self.closed = True


def create_fixture(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO targets VALUES (
                '3:1:2','Alpha',9000,3,1,2,1,0,'',700000,800000,12,
                '2026-08-08T07:00:00+00:00',4,'2026-08-08T06:00:00+00:00',NULL
            )
            """
        )
        conn.execute("INSERT INTO queue VALUES (1,'3:1:2',1,'queued')")
        conn.execute(
            """
            INSERT INTO history VALUES (
                1,'3:39:11','3:1:2','Alpha',25,'2026-08-08T06:00:00+00:00',
                NULL,'2026-08-08T08:00:00+00:00','sent',NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO spy_reports VALUES (
                1,'m1','d1','3:1:2','2026-08-08T07:00:00+00:00',9000,
                700000,800000,12,100,5,6,'full','messages',
                '2026-08-08T07:01:00+00:00','{}'
            )
            """
        )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nemexia_qt_smoke_", ignore_cleanup_errors=True) as temp:
        root = Path(temp)
        legacy_db = root / "legacy.sqlite3"
        create_fixture(legacy_db)
        before = legacy_db.read_bytes()

        paths = ensure_runtime_paths(
            build_runtime_paths(
                env={"LOCALAPPDATA": str(root / "local")},
                platform_name="nt",
                home=root,
            )
        )
        live_source = FakeLiveFlightSource()
        context = V2ApplicationContext(legacy_db, flight_source=live_source)
        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(ORBITAL_COMMAND_QSS)
        window = MainWindow(paths, context)
        try:
            assert window.minimumWidth() == 1180
            assert window.minimumHeight() == 720
            assert window.stack.count() == 11

            expected = {
                "overview": "OverviewPage",
                "plan": "PlanPage",
                "active": "ActivePage",
                "recon": "ReconPage",
                "targets": "TargetsPage",
                "history": "HistoryPage",
                "diagnostics": "DiagnosticsPage",
            }
            for key, class_name in expected.items():
                page = window.stack.widget(window._page_index[key])
                assert page.__class__.__name__ == class_name, (key, page.__class__.__name__)

            plan = window.stack.widget(window._page_index["plan"])
            active = window.stack.widget(window._page_index["active"])
            recon = window.stack.widget(window._page_index["recon"])
            targets = window.stack.widget(window._page_index["targets"])
            history = window.stack.widget(window._page_index["history"])
            diagnostics = window.stack.widget(window._page_index["diagnostics"])

            assert plan.model.rowCount() == 1
            assert recon.model.rowCount() == 1
            assert targets.model.rowCount() == 1
            assert history.model.rowCount() == 1

            # Building the shell must not probe CDP before the user opens Active.
            assert live_source.status_reads == 0
            assert live_source.refreshes == 0
            assert active.model.rowCount() == 0

            window._show_page("active", "Активные", "Текущие полёты и возвраты")
            app.processEvents()
            assert live_source.refreshes == 1
            assert live_source.status_reads == 1
            assert active.model.rowCount() == 2
            assert active.capacity is not None
            assert (active.capacity.used, active.capacity.maximum, active.capacity.free) == (20, 22, 2)
            assert "20 / 22" in active.capacity_label.text()

            # Diagnostics reflects the cached result and must not probe the browser itself.
            window._show_page("diagnostics", "Диагностика", "Логи и техническое состояние")
            app.processEvents()
            assert live_source.status_reads == 1
            assert diagnostics.live_status_value.text() == "Доступны"
            assert "fixture CDP" in diagnostics.live_detail_value.text()

            window.show()
            app.processEvents()
        finally:
            window.close()
            app.processEvents()
            context.close()

        assert live_source.closed is True
        assert legacy_db.read_bytes() == before
        assert not paths.database.exists(), "V2 preview must not create its own SQLite yet"

    print("OK: PySide6 V2 fourth-batch live-read offscreen smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
