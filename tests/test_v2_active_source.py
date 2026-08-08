from __future__ import annotations

from pathlib import Path

from v2.application.context import V2ApplicationContext
from v2.application.flight_source import ActiveFlightSnapshot, FlightSourceStatus


class FakeFlightSource:
    def status(self) -> FlightSourceStatus:
        return FlightSourceStatus(True, "fixture live source")

    def flights(self):
        return (
            ActiveFlightSnapshot(
                source="3:39:11",
                target="3:1:2",
                mission="Атака",
                departure_at="2026-08-08T09:00:00+00:00",
                arrival_at="2026-08-08T09:10:00+00:00",
                return_at="2026-08-08T09:20:00+00:00",
                fleet_id="42",
            ),
        )


def test_default_source_is_explicitly_unavailable(tmp_path: Path) -> None:
    context = V2ApplicationContext(tmp_path / "missing.sqlite3")
    try:
        assert context.flight_status().available is False
        assert "not connected" in context.flight_status().detail
        assert context.active_flights() == []
    finally:
        context.close()


def test_injected_read_source_passes_live_facts_without_browser_dependency(tmp_path: Path) -> None:
    context = V2ApplicationContext(tmp_path / "missing.sqlite3", flight_source=FakeFlightSource())
    try:
        assert context.flight_status().available is True
        flights = context.active_flights()
        assert len(flights) == 1
        assert flights[0].source == "3:39:11"
        assert flights[0].mission == "Атака"
        assert flights[0].fleet_id == "42"
    finally:
        context.close()


def test_active_ui_uses_typed_semantics_and_does_not_claim_zero_when_unavailable() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / "v2" / "ui" / "pages" / "active.py").read_text(encoding="utf-8")
    main = (root / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "Live-полёты не проверены" in page
    assert "Live-полёты пока не подключены" in page
    assert "context.refresh_live_source()" in page
    assert "context.classified_active_flights() if status.available else []" in page
    assert "Направление" in page
    assert "В расчётах" in page
    assert "Таймер фарма" in page
    assert "item.facts.direction.value" in page
    assert "item.facts.owner_scope.value" in page
    assert "item.facts.excluded" in page
    assert "item.facts.blocks_farm_cycle" in page
    assert "Обновить" in page
    assert 'if key == "active"' in main
    assert "ActivePage(self.context" in main
    for forbidden in ("BrowserWorker", "send_raid", "prepare_raid", "FleetsCount", "MaxFleets"):
        assert forbidden not in page
