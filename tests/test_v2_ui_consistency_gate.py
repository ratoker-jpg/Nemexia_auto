from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "v2" / "ui"
SMOKE = (ROOT / "ci" / "qt_smoke.py").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "run_app.bat").read_text(encoding="utf-8")


def _all_ui_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(UI_ROOT.rglob("*.py")))


def test_qt_smoke_covers_both_supported_geometries_and_all_pages() -> None:
    assert "GEOMETRIES = ((1180, 720), (1440, 900))" in SMOKE
    for key in (
        "overview", "plan", "active", "farm", "asteroids", "debris",
        "recon", "targets", "history", "settings", "diagnostics",
    ):
        assert f'"{key}":' in SMOKE
    assert "window.stack.setCurrentIndex(index)" in SMOKE
    assert "minimumSizeHint()" in SMOKE
    assert "Settings must scroll instead of forcing the main window larger" in SMOKE
    assert "Diagnostics must scroll instead of forcing the main window larger" in SMOKE
    assert "farm._armed is False" in SMOKE
    assert "farm._timer.isActive() is False" in SMOKE


def test_entire_v2_ui_tree_has_no_browser_navigation_primitives() -> None:
    source = _all_ui_source()
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
    ):
        assert forbidden not in source


def test_default_launcher_remains_legacy_tk_entrypoint() -> None:
    assert '"%VENV_PY%" app_entry.py' in LAUNCHER
    assert "app_qt.py" not in LAUNCHER
