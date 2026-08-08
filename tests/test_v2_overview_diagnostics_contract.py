from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
OVERVIEW = (ROOT / "v2" / "ui" / "pages" / "overview.py").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "v2" / "ui" / "pages" / "diagnostics.py").read_text(encoding="utf-8")


def test_overview_and_diagnostics_replace_placeholders() -> None:
    assert 'if key == "overview"' in MAIN
    assert "OverviewPage(self.context" in MAIN
    assert 'if key == "diagnostics"' in MAIN
    assert "DiagnosticsPage(self.context, self.runtime_paths" in MAIN


def test_overview_uses_persisted_and_cached_application_snapshots() -> None:
    assert "context.overview()" in OVERVIEW
    for field in (
        "targets_total",
        "targets_enabled",
        "queue_queued",
        "history_total",
        "latest_spy_at",
        "latest_raid_at",
    ):
        assert field in OVERVIEW
    assert "FleetsCount" not in OVERVIEW
    assert "22" not in OVERVIEW
    assert "BrowserWorker" not in OVERVIEW


def test_diagnostics_is_transparent_about_legacy_readonly_and_v2_owned_paths() -> None:
    assert "context.status()" in DIAGNOSTICS
    assert "runtime_paths.root" in DIAGNOSTICS
    assert "runtime_paths.database" in DIAGNOSTICS
    assert "runtime_paths.browser_profile" in DIAGNOSTICS
    assert "Legacy SQLite режим" in DIAGNOSTICS
    assert "V2 SQLite" in DIAGNOSTICS
    assert "V2 settings" in DIAGNOSTICS
    assert "V2 isolated writes + legacy/browser read-only" in DIAGNOSTICS
    assert "send_raid" not in DIAGNOSTICS
