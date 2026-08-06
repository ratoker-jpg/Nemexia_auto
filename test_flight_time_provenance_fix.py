from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flight_time_provenance_fix import (
    _derive_sent_at_source,
    install_flight_time_provenance_fix,
)
from models import Flight
from storage import Database


class FlightTimeProvenanceFixTest(unittest.TestCase):
    def test_provenance_derivation(self) -> None:
        self.assertEqual(_derive_sent_at_source({}), "unknown")
        self.assertEqual(_derive_sent_at_source({"sent_at": "2026-08-06T18:00:00+00:00"}), "inferred")
        self.assertEqual(
            _derive_sent_at_source({
                "sent_at": "2026-08-06T18:00:00+00:00",
                "one_way_seconds": 60,
            }),
            "exact",
        )
        self.assertEqual(
            _derive_sent_at_source({"sent_at_source": "inferred", "one_way_seconds": 60}),
            "inferred",
        )

    def test_database_migration_and_exact_send_persistence(self) -> None:
        install_flight_time_provenance_fix()
        with tempfile.TemporaryDirectory(prefix="nemexia_provenance_") as temp:
            db = Database(Path(temp) / "test.sqlite3")
            columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(history)")}
            self.assertIn("sent_at_source", columns)
            now = datetime.now(timezone.utc)
            row_id = db.add_history({
                "fleet_id": "exact-1",
                "source": "3:39:11",
                "target": "3:1:1",
                "sent_at": now.isoformat(),
                "arrival_at": (now + timedelta(minutes=1)).isoformat(),
                "return_at": (now + timedelta(minutes=2)).isoformat(),
                "one_way_seconds": 60,
                "round_trip_seconds": 120,
            })
            row = db.conn.execute("SELECT sent_at_source FROM history WHERE id=?", (row_id,)).fetchone()
            self.assertEqual(row["sent_at_source"], "exact")
            db.close()

    def test_flight_model_carries_inferred_marker(self) -> None:
        flight = Flight(
            "fleet-1", "3:39:11", "3:1:1", "Атака",
            datetime.now(timezone.utc), datetime.now(timezone.utc),
            sent_at_source="inferred",
        )
        self.assertEqual(flight.sent_at_source, "inferred")


if __name__ == "__main__":
    unittest.main()
