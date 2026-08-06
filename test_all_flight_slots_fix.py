from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from all_flight_slots_fix import _active_attack_coords, _is_attack, _sync_all_for_capacity


class FakeWorker:
    def __init__(self, flights):
        self.flights = flights

    async def sync_all_flights(self):
        return self.flights


class AllFlightSlotsFixTest(unittest.TestCase):
    def test_capacity_sync_returns_every_mission(self) -> None:
        flights = [
            SimpleNamespace(mission="Атака", target="3:1:1"),
            SimpleNamespace(mission="Добыча газа", target="3:2:2"),
            SimpleNamespace(mission="Транспортировка", target="3:3:3"),
        ]
        result = asyncio.run(_sync_all_for_capacity(FakeWorker(flights)))
        self.assertEqual(len(result), 3)

    def test_duplicate_protection_uses_attacks_only(self) -> None:
        app = SimpleNamespace(active_flights=[
            SimpleNamespace(mission="Атака", target="3:1:1"),
            SimpleNamespace(mission="Добыча газа", target="3:2:2"),
            SimpleNamespace(mission="Транспортировка", target="3:3:3"),
        ])
        self.assertEqual(_active_attack_coords(app), {"3:1:1"})

    def test_attack_match_is_case_and_space_tolerant(self) -> None:
        self.assertTrue(_is_attack(SimpleNamespace(mission="  АТАКА  ")))
        self.assertFalse(_is_attack(SimpleNamespace(mission="Добыча газа")))


if __name__ == "__main__":
    unittest.main()
