from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
MAIN_WINDOW = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
THEME = (ROOT / "v2" / "ui" / "theme.py").read_text(encoding="utf-8")
LEGACY_RUNNER = (ROOT / "run_app.bat").read_text(encoding="utf-8")
V2_REQUIREMENTS = (ROOT / "requirements-v2.txt").read_text(encoding="utf-8")


def test_qt_sources_compile_without_importing_pyside() -> None:
    compile(APP_QT, "app_qt.py", "exec")
    compile(MAIN_WINDOW, "v2/ui/main_window.py", "exec")
    compile(THEME, "v2/ui/theme.py", "exec")


def test_v2_dependencies_are_separate_from_legacy_requirements() -> None:
    assert "-r requirements.txt" in V2_REQUIREMENTS
    assert "PySide6" in V2_REQUIREMENTS


def test_legacy_runner_still_launches_legacy_entrypoint() -> None:
    assert '"%VENV_PY%" app_entry.py' in LEGACY_RUNNER
    assert "app_qt.py" not in LEGACY_RUNNER


def test_qt_entrypoint_uses_isolated_v2_runtime_paths() -> None:
    assert "ensure_runtime_paths(build_runtime_paths())" in APP_QT
    assert "requirements-v2.txt" in APP_QT


def test_shell_contains_planned_navigation_without_game_actions() -> None:
    for label in (
        "Обзор",
        "План",
        "Активные",
        "Автофарм",
        "Астероиды",
        "Обломки",
        "Разведка",
        "Цели",
        "История",
        "Настройки",
        "Диагностика",
    ):
        assert label in MAIN_WINDOW
    assert "send_raid" not in MAIN_WINDOW
    assert "BrowserWorker" not in MAIN_WINDOW
