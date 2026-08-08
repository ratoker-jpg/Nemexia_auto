from __future__ import annotations

from pathlib import Path

from v2.application.browser_read_service import (
    BrowserFleetCapacity,
    BrowserReadStatus,
    V2BrowserFlightSource,
)


class CapacityBackend:
    def status(self) -> BrowserReadStatus:
        return BrowserReadStatus(True, detail="connected")

    def flights(self):
        return ()

    def capacity(self) -> BrowserFleetCapacity:
        return BrowserFleetCapacity(used=20, maximum=22)


def test_capacity_maps_game_counter_without_counting_flight_rows() -> None:
    source = V2BrowserFlightSource(CapacityBackend())
    capacity = source.capacity()
    assert capacity is not None
    assert capacity.used == 20
    assert capacity.maximum == 22
    assert capacity.free == 2
    assert "FleetsCount" in capacity.source
    assert source.flights() == ()


def test_invalid_capacity_fails_closed() -> None:
    class InvalidBackend(CapacityBackend):
        def capacity(self) -> BrowserFleetCapacity:
            return BrowserFleetCapacity(used=23, maximum=22)

    assert V2BrowserFlightSource(InvalidBackend()).capacity() is None


def test_capacity_contract_never_derives_slots_from_flight_row_count() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "v2" / "application" / "browser_read_service.py").read_text(encoding="utf-8")
    active = (root / "v2" / "ui" / "pages" / "active.py").read_text(encoding="utf-8")
    assert "BrowserFleetCapacity" in service
    assert "capacity.used" in active
    assert "capacity.maximum" in active
    for forbidden in (
        "len(self._backend.flights())",
        "len(context.active_flights())",
        "maximum - len(",
        "max_slots - len(",
    ):
        assert forbidden not in service
        assert forbidden not in active
