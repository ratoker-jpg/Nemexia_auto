from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SMOKE = (ROOT / "ci" / "release_default_launcher_smoke.py").read_text(encoding="utf-8")
FALLBACK_SMOKE = (ROOT / "ci" / "release_fallback_smoke.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RUN_DEFAULT = (ROOT / "run_app.bat").read_text(encoding="utf-8")
RUN_LEGACY = (ROOT / "run_legacy.bat").read_text(encoding="utf-8")


def test_post_cutover_ci_executes_both_default_and_fallback_batch_launchers() -> None:
    assert "Run default Qt launcher smoke" in WORKFLOW
    assert r"run: .venv\Scripts\python.exe ci\release_default_launcher_smoke.py" in WORKFLOW
    assert "Run explicit legacy fallback smoke" in WORKFLOW
    assert r"run: .venv\Scripts\python.exe ci\release_fallback_smoke.py" in WORKFLOW


def test_default_black_box_smoke_bootstraps_only_v2_storage() -> None:
    assert '["cmd", "/d", "/c", "run_app.bat", "--release-smoke"]' in DEFAULT_SMOKE
    assert 'profile / "NemexiaRaidManagerV2"' in DEFAULT_SMOKE
    assert 'profile / "NemexiaRaidManager"' in DEFAULT_SMOKE
    assert "assert not legacy_root.exists()" in DEFAULT_SMOKE
    assert "PRAGMA user_version" in DEFAULT_SMOKE
    assert "PRAGMA integrity_check" in DEFAULT_SMOKE


def test_default_and_fallback_remain_strictly_split() -> None:
    assert '"%VENV_PY%" app_qt.py %*' in RUN_DEFAULT
    assert "app_entry.py" not in RUN_DEFAULT
    assert '"%VENV_PY%" app_entry.py %*' in RUN_LEGACY
    assert "app_qt.py" not in RUN_LEGACY
    assert 'profile / "NemexiaRaidManagerV2"' in FALLBACK_SMOKE
    assert "assert not v2_root.exists()" in FALLBACK_SMOKE


def test_post_cutover_gate_does_not_add_browser_navigation() -> None:
    for forbidden in (
        "launch_yandex(",
        "change_planet.php",
        "refreshGalaxy(",
        ".goto(",
        "new_page(",
    ):
        assert forbidden not in DEFAULT_SMOKE + FALLBACK_SMOKE
