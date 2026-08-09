from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "v2" / "release_lifecycle.py").read_text(encoding="utf-8")
RUN_APP = (ROOT / "run_app.bat").read_text(encoding="utf-8")
RUN_LEGACY = (ROOT / "run_legacy.bat").read_text(encoding="utf-8")


def test_qt_entrypoint_uses_mandatory_production_session() -> None:
    assert "from v2.release_lifecycle import ReleaseLifecycleError, V2ProductionSession" in APP_QT
    assert "with V2ProductionSession(paths, build_context) as context:" in APP_QT
    assert "run_qt_app(paths, context)" in APP_QT
    assert "V2 production lifecycle stopped:" in APP_QT


def test_production_session_backs_up_before_returning_context_and_before_close() -> None:
    startup_backup = LIFECYCLE.index("self.startup_backup = self._backup_factory")
    enter_return = LIFECYCLE.index("return context", startup_backup)
    shutdown_backup = LIFECYCLE.index("self.shutdown_backup = self._backup_factory")
    context_close = LIFECYCLE.index("context.close()", shutdown_backup)
    assert startup_backup < enter_return
    assert shutdown_backup < context_close
    assert "create_v2_backup" in LIFECYCLE
    assert "finally:\n            context.close()" in LIFECYCLE


def test_authorized_default_qt_still_uses_release_lifecycle_without_navigation() -> None:
    assert '"%VENV_PY%" app_qt.py %*' in RUN_APP
    assert "app_entry.py" not in RUN_APP
    assert '"%VENV_PY%" app_entry.py %*' in RUN_LEGACY
    for forbidden in (
        "launch_yandex(",
        ".goto(",
        "refreshGalaxy(",
        "change_planet.php",
        "new_page(",
    ):
        assert forbidden not in LIFECYCLE
