from __future__ import annotations

from pathlib import Path

from v2.application.browser_read_service import (
    BrowserFlightRecord,
    BrowserReadStatus,
    V2BrowserFlightSource,
)


class FakeBackend:
    def __init__(self, status: BrowserReadStatus) -> None:
        self._status = status
        self.flight_reads = 0

    def status(self) -> BrowserReadStatus:
        return self._status

    def flights(self):
        self.flight_reads += 1
        return (
            BrowserFlightRecord(
                source="3:39:11",
                target="3:1:2",
                mission="Атака",
                departure_at="2026-08-08T09:00:00+00:00",
                arrival_at="2026-08-08T09:10:00+00:00",
                return_at="2026-08-08T09:20:00+00:00",
                fleet_id="77",
            ),
        )


def test_disconnected_backend_is_unavailable_and_not_read() -> None:
    backend = FakeBackend(BrowserReadStatus(False, endpoint="http://127.0.0.1:9222", detail="offline"))
    source = V2BrowserFlightSource(backend)
    assert source.status().available is False
    assert source.flights() == ()
    assert backend.flight_reads == 0


def test_captcha_is_fail_closed_for_live_flight_reads() -> None:
    backend = FakeBackend(BrowserReadStatus(True, captcha_present=True, detail="CAPTCHA detected"))
    source = V2BrowserFlightSource(backend)
    assert source.status().available is False
    assert "CAPTCHA" in source.status().detail
    assert source.flights() == ()
    assert backend.flight_reads == 0


def test_connected_backend_maps_neutral_records_to_flight_source() -> None:
    backend = FakeBackend(BrowserReadStatus(True, endpoint="http://127.0.0.1:9222", detail="connected"))
    source = V2BrowserFlightSource(backend)
    assert source.status().available is True
    flights = source.flights()
    assert len(flights) == 1
    assert flights[0].source == "3:39:11"
    assert flights[0].target == "3:1:2"
    assert flights[0].fleet_id == "77"
    assert backend.flight_reads == 1


def test_boundary_does_not_import_or_expose_legacy_action_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "application" / "browser_read_service.py").read_text(encoding="utf-8")
    assert "from browser import" not in source
    assert "import browser" not in source
    for forbidden in (
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "_select_planet",
        "goto",
    ):
        assert forbidden not in source
