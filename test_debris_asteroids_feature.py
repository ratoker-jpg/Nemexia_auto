from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime
from types import SimpleNamespace

from debris_asteroids_feature import (
    _load_debris_observations,
    _replace_debris_observations,
    asteroid_has_debris,
    debris_scan_sequence,
)
from models import AsteroidObservation


class DebrisAsteroidsFeatureTest(unittest.TestCase):
    def test_debris_marker_matches_saved_tooltip_wording(self) -> None:
        tooltip = """
            <b>Информация об астероиде</b><br>
            Последнее перемещение 2026-08-06 20:45:08<br>
            Следующее перемещение 2026-08-06 21:46:08<br>
            Скорость 61 Минут / поле<br>
            Этот астероид содержит обломки
        """
        self.assertTrue(asteroid_has_debris(tooltip))
        self.assertFalse(asteroid_has_debris(tooltip.replace("Этот астероид содержит обломки", "")))

    def test_scan_sequence_covers_three_galaxies_and_120_systems(self) -> None:
        sequence = debris_scan_sequence()
        self.assertEqual(len(sequence), 120)
        self.assertEqual(sequence[0], (1, 40))
        self.assertEqual(sequence[39], (1, 1))
        self.assertEqual(sequence[40], (2, 40))
        self.assertEqual(sequence[-1], (3, 1))
        self.assertEqual(len(set(sequence)), 120)

    def test_saved_scan_round_trip(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db = SimpleNamespace(conn=connection)
        observation = AsteroidObservation(
            g=1,
            s=23,
            p=8,
            last_move_server=datetime(2026, 8, 6, 20, 45, 8),
            next_move_server=datetime(2026, 8, 6, 21, 46, 8),
            period_seconds=61 * 60,
            scanned_server_at=datetime(2026, 8, 6, 20, 57, 38),
            tooltip_html="Этот астероид содержит обломки",
            status="debris",
        )
        _replace_debris_observations(db, [observation])
        restored = _load_debris_observations(db)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].coord, "1:23:8")
        self.assertEqual(restored[0].period_seconds, 3660)
        self.assertEqual(restored[0].status, "debris")
        connection.close()


if __name__ == "__main__":
    unittest.main()
