from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = (ROOT / "v2" / "ui" / "pages" / "overview.py").read_text(encoding="utf-8")


def test_overview_uses_shared_operational_components() -> None:
    for primitive in ("MetricCard", "StateBanner", "SectionCard", "command_button", "page_layout"):
        assert primitive in OVERVIEW
    assert "Live readiness" in OVERVIEW
    assert "Последние сохранённые события" in OVERVIEW
    assert "Обновить live" in OVERVIEW


def test_overview_keeps_refresh_explicit_and_attach_only() -> None:
    assert "context.overview()" in OVERVIEW
    assert "self.context.refresh_live_source()" in OVERVIEW
    assert "self.context.live_overview_snapshot()" in OVERVIEW
    assert OVERVIEW.index("clicked.connect(self.refresh_live)") < OVERVIEW.index("def refresh_live")
    for forbidden in ("BrowserWorker", "playwright", "goto(", "new_page(", "refreshGalaxy", "SendFleet"):
        assert forbidden not in OVERVIEW
