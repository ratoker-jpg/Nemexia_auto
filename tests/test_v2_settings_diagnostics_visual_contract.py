from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = (ROOT / "v2" / "ui" / "pages" / "settings.py").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "v2" / "ui" / "pages" / "diagnostics.py").read_text(encoding="utf-8")


def test_settings_is_scrollable_grouped_and_uses_only_current_fields() -> None:
    for token in (
        "scrollable_page",
        "Connection",
        "Account context",
        "Farm timing",
        "Safety gate",
        "CDP port",
        "Планета автофарма",
        "Командная планета",
        "Буфер после возврата",
        "Разрешить действия V2",
        "NO NAVIGATION BOUNDARY",
    ):
        assert token in SETTINGS
    assert "context.v2_settings_snapshot()" in SETTINGS
    assert "self.context.set_v2_settings(values)" in SETTINGS


def test_diagnostics_remains_cached_no_probe_and_selectable() -> None:
    for token in (
        "No-probe diagnostics",
        "scrollable_page",
        "SectionCard",
        "TextSelectableByMouse",
        "context.status()",
        "self.context.cached_flight_status()",
        "runtime_paths.root",
        "runtime_paths.database",
        "runtime_paths.browser_profile",
        "Legacy SQLite режим",
        "V2 isolated writes + legacy/browser read-only",
    ):
        assert token in DIAGNOSTICS
    assert "refresh_live_source" not in DIAGNOSTICS


def test_settings_diagnostics_add_no_browser_or_direct_storage_capability() -> None:
    combined = SETTINGS + DIAGNOSTICS
    for forbidden in (
        "from browser import",
        "import browser",
        "BrowserWorker",
        "playwright",
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "change_planet.php",
        "launch_yandex(",
        "sqlite3",
        "INSERT INTO",
        "UPDATE settings",
        "DELETE FROM",
    ):
        assert forbidden not in combined
