from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.bat").read_text(encoding="utf-8")
RUN_DEFAULT = (ROOT / "run_app.bat").read_text(encoding="utf-8")
RUN_QT = (ROOT / "run_qt.bat").read_text(encoding="utf-8")
BUILD_REQ = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
LEGACY_SPEC = (ROOT / "NemexiaRaidManager.spec").read_text(encoding="utf-8")
QT_SPEC = (ROOT / "NemexiaRaidManagerQt.spec").read_text(encoding="utf-8")
BUILD_LEGACY = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
BUILD_QT = (ROOT / "build_qt_exe.bat").read_text(encoding="utf-8")


def test_installer_prepares_one_environment_for_legacy_and_qt() -> None:
    assert "pip install -r requirements-v2.txt" in INSTALL
    assert "compileall -q" in INSTALL
    assert "app_entry.py" in INSTALL
    assert "app_qt.py" in INSTALL
    assert "import PySide6, app_qt" in INSTALL
    assert '"%VENV_PY%" self_test.py' in INSTALL


def test_rel03_keeps_legacy_default_but_adds_explicit_qt_launcher() -> None:
    assert '"%VENV_PY%" app_entry.py' in RUN_DEFAULT
    assert "app_qt.py" not in RUN_DEFAULT
    assert '"%VENV_PY%" app_qt.py' in RUN_QT
    assert "app_entry.py" not in RUN_QT
    assert "install.bat" in RUN_QT


def test_build_environment_and_specs_are_side_by_side() -> None:
    assert "-r requirements-v2.txt" in BUILD_REQ
    assert "['app_entry.py']" in LEGACY_SPEC
    assert "name='NemexiaRaidManager'" in LEGACY_SPEC
    assert "['app_qt.py']" in QT_SPEC
    assert "PySide6.QtWidgets" in QT_SPEC
    assert "name='NemexiaRaidManagerQt'" in QT_SPEC
    assert "NemexiaRaidManager.spec" in BUILD_LEGACY
    assert "NemexiaRaidManagerQt.spec" in BUILD_QT
    assert "dist\\NemexiaRaidManagerQt.exe" in (ROOT / "launcher_messages.ps1").read_text(encoding="utf-8")


def test_qt_release_prep_does_not_add_navigation_commands() -> None:
    combined = RUN_QT + BUILD_QT + QT_SPEC + INSTALL
    for forbidden in (
        "launch_yandex",
        "change_planet.php",
        "refreshGalaxy",
        ".goto(",
    ):
        assert forbidden not in combined
