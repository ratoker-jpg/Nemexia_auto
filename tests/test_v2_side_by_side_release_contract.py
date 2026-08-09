from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
SMOKE = (ROOT / "ci" / "release_side_by_side_smoke.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RUN_DEFAULT = (ROOT / "run_app.bat").read_text(encoding="utf-8")


def test_both_production_entrypoints_have_noninteractive_release_smoke() -> None:
    assert '"--release-smoke" in sys.argv' in APP_ENTRY
    assert "return release_smoke()" in APP_ENTRY
    assert '"--release-smoke" in sys.argv' in APP_QT
    assert "return release_smoke(paths)" in APP_QT
    assert "V2ProductionSession(paths, build_context)" in APP_QT
    assert "run_qt_app(paths, context)" not in APP_QT[APP_QT.index("def release_smoke"):APP_QT.index("def main")]
    assert "RaidManagerApp()" not in APP_ENTRY[APP_ENTRY.index("def release_smoke"):APP_ENTRY.index("def main")]


def test_release_smoke_runs_clean_and_existing_user_profiles() -> None:
    assert '_clean_install(root / "clean")' in SMOKE
    assert '_existing_user_upgrade(root / "upgrade")' in SMOKE
    assert '"app_qt.py"' in SMOKE
    assert '"app_entry.py"' in SMOKE
    assert 'legacy_db.read_bytes() == legacy_before_qt' in SMOKE
    assert 'settings.get("cdp_port") == 9333' in SMOKE
    assert 'settings.get("farm_home") == "3:39:11"' in SMOKE
    assert 'settings.get("farm_return_buffer_minutes") == 9' in SMOKE
    assert "len(database.list_raid_queue_rows()) == 5" in SMOKE
    assert "len(database.list_recon_target_rows()) > 0" in SMOKE


def test_ci_uses_real_installer_and_installed_venv_for_side_by_side_gate() -> None:
    assert "release-side-by-side:" in WORKFLOW
    assert "name: Windows clean install + existing-user upgrade" in WORKFLOW
    assert "run: install.bat" in WORKFLOW
    assert r"run: .venv\Scripts\python.exe ci\release_side_by_side_smoke.py" in WORKFLOW


def test_rel04_still_does_not_cut_over_default_or_add_navigation() -> None:
    assert '"%VENV_PY%" app_entry.py' in RUN_DEFAULT
    assert "app_qt.py" not in RUN_DEFAULT
    for forbidden in (
        "launch_yandex(",
        "change_planet.php",
        "refreshGalaxy(",
        ".goto(",
        "new_page(",
    ):
        assert forbidden not in SMOKE
