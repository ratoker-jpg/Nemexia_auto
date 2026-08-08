from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from v2.infrastructure.cdp_read_backend import (
    _DomFlightRow,
    extract_coord,
    map_dom_flight,
    parse_counter,
    parse_hms,
)


def test_readonly_cdp_parsers_match_verified_fleet_dom_semantics() -> None:
    assert parse_hms("01:02:03") == 3723
    assert parse_hms("02:03") == 123
    assert parse_hms("—") is None
    assert extract_coord("Planet [ 3 : 39 : 11 ]") == "3:39:11"
    assert parse_counter(" 20 ") == 20
    assert parse_counter("22") == 22


def test_dom_flight_maps_countdowns_without_game_actions() -> None:
    now = datetime(2026, 8, 8, 9, 0, 0, tzinfo=timezone.utc)
    record = map_dom_flight(
        _DomFlightRow(
            fleet_id="77",
            source="[3:39:11]",
            target="[3:1:2]",
            mission="Атака",
            arrival="00:10:00",
            returning="00:20:00",
        ),
        now=now,
    )
    assert record is not None
    assert record.source == "3:39:11"
    assert record.target == "3:1:2"
    assert record.mission == "Атака"
    assert record.fleet_id == "77"
    assert record.departure_at == "2026-08-08T09:00:00+00:00"
    assert record.arrival_at == "2026-08-08T09:10:00+00:00"
    assert record.return_at == "2026-08-08T09:20:00+00:00"


def test_adapter_is_attach_only_and_reads_verified_capacity_selectors() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_read_backend.py").read_text(encoding="utf-8")

    assert "connect_over_cdp" in source
    assert "#fleetHandler tbody tr" in source
    assert "#FleetsCount" in source
    assert "#MaxFleets" in source
    assert "fleets.php" in source
    assert "Browser.close()" in source  # explicit guard comment: never call it

    for forbidden in (
        "from browser import",
        "import browser",
        "BrowserWorker",
        "launch_yandex",
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "showFleets()",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "bring_to_front(",
    ):
        assert forbidden not in source
