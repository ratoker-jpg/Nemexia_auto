from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = (ROOT / "v2" / "ui" / "theme.py").read_text(encoding="utf-8")
COMPONENTS = (ROOT / "v2" / "ui" / "components.py").read_text(encoding="utf-8")
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
READINESS = (ROOT / "v2" / "ui" / "browser_readiness_panel.py").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "run_app.bat").read_text(encoding="utf-8")
LEGACY_LAUNCHER = (ROOT / "run_legacy.bat").read_text(encoding="utf-8")


def test_design_tokens_are_explicit_and_reusable() -> None:
    for token in ("COLORS", "SPACING", "RADII", "SIZES", "TYPOGRAPHY"):
        assert token in THEME
    assert '"xs": 4' in THEME
    assert '"sm": 8' in THEME
    assert '"md": 12' in THEME
    assert '"lg": 16' in THEME
    assert '"xl": 24' in THEME
    assert '"xxl": 32' in THEME
    assert '"sidebar": 220' in THEME
    assert '"topbar": 80' in THEME


def test_design_system_exposes_semantic_visual_primitives() -> None:
    for primitive in (
        "StatusPill",
        "MetricCard",
        "StateBanner",
        "SectionCard",
        "EmptyState",
        "command_button",
        "page_layout",
        "scrollable_page",
        "toolbar",
    ):
        assert primitive in COMPONENTS
    for tone in ('tone="primary"', 'tone="warning"', 'tone="danger"', 'tone="ghost"'):
        assert tone in THEME
    assert 'compact="true"' in THEME
    assert "QMessageBox" in THEME
    assert "QScrollBar:horizontal" in THEME


def test_component_and_shell_layers_do_not_gain_browser_or_mutation_capabilities() -> None:
    combined = THEME + COMPONENTS + MAIN
    for forbidden in (
        "BrowserWorker",
        "playwright",
        "new_page(",
        ".goto(",
        "refreshGalaxy",
        "change_planet.php",
        "launch_yandex",
        "SendFleet",
        "processSpy",
        "sqlite3",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ):
        assert forbidden not in combined


def test_shell_preserves_routes_sizes_with_qt_default_and_legacy_fallback() -> None:
    for label in (
        "Обзор", "План", "Активные", "Автофарм", "Астероиды", "Обломки",
        "Разведка", "Цели", "История", "Настройки", "Диагностика",
    ):
        assert label in MAIN
    assert "setMinimumSize(1180, 720)" in MAIN
    assert "resize(1440, 900)" in MAIN
    assert "BrowserReadinessPanel(self.context" in MAIN
    for state in ("Browser", "Account", "Planet", "Fleets", "Messages", "Galaxy"):
        assert f'"{state}"' in READINESS
    assert '"%VENV_PY%" app_qt.py %*' in LAUNCHER
    assert "app_entry.py" not in LAUNCHER
    assert '"%VENV_PY%" app_entry.py %*' in LEGACY_LAUNCHER
    assert "app_qt.py" not in LEGACY_LAUNCHER
