from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_DEFAULT = (ROOT / "run_app.bat").read_text(encoding="utf-8")
RUN_QT = (ROOT / "run_qt.bat").read_text(encoding="utf-8")
RUN_LEGACY = (ROOT / "run_legacy.bat").read_text(encoding="utf-8")
DEFAULT_SPEC = (ROOT / "NemexiaRaidManager.spec").read_text(encoding="utf-8")
LEGACY_SPEC = (ROOT / "NemexiaRaidManagerLegacy.spec").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "v2" / "release_lifecycle.py").read_text(encoding="utf-8")


def test_default_source_launcher_is_qt_and_fallback_is_legacy() -> None:
    assert '"%VENV_PY%" app_qt.py %*' in RUN_DEFAULT
    assert "app_entry.py" not in RUN_DEFAULT
    assert '"%VENV_PY%" app_qt.py' in RUN_QT
    assert "app_entry.py" not in RUN_QT
    assert '"%VENV_PY%" app_entry.py %*' in RUN_LEGACY
    assert "app_qt.py" not in RUN_LEGACY


def test_default_packaged_app_is_qt_and_legacy_package_remains_explicit() -> None:
    assert "['app_qt.py']" in DEFAULT_SPEC
    assert "name='NemexiaRaidManager'" in DEFAULT_SPEC
    assert "PySide6.QtWidgets" in DEFAULT_SPEC
    assert "['app_entry.py']" in LEGACY_SPEC
    assert "name='NemexiaRaidManagerLegacy'" in LEGACY_SPEC


def test_cutover_keeps_mandatory_v2_lifecycle_and_navigation_boundary() -> None:
    assert "create_v2_backup" in LIFECYCLE
    assert "self.startup_backup" in LIFECYCLE
    assert "self.shutdown_backup" in LIFECYCLE
    for forbidden in (
        "launch_yandex(",
        ".goto(",
        "refreshGalaxy(",
        "change_planet.php",
        "new_page(",
    ):
        assert forbidden not in RUN_DEFAULT + DEFAULT_SPEC + LIFECYCLE
