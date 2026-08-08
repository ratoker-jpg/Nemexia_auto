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
        context = V2ApplicationContext(legacy_db)
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

            assert plan.model.rowCount() == 1
            assert recon.model.rowCount() == 1
            assert targets.model.rowCount() == 1
            assert history.model.rowCount() == 1

            # No live backend is injected in preview mode. This is explicitly
            # unavailable data, not a factual claim that the account has zero flights.
            assert context.flight_status().available is False
            assert active.model.rowCount() == 0

            window.show()
            app.processEvents()
        finally:
            window.close()
            app.processEvents()
            context.close()

        assert legacy_db.read_bytes() == before
        assert not paths.database.exists(), "V2 preview must not create its own SQLite yet"

    print("OK: PySide6 V2 third-batch offscreen smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
