from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_DEFAULT = (ROOT / "run_app.bat").read_text(encoding="utf-8")
RUN_LEGACY = (ROOT / "run_legacy.bat").read_text(encoding="utf-8")
RUN_QT = (ROOT / "run_qt.bat").read_text(encoding="utf-8")
FALLBACK_SMOKE = (ROOT / "ci" / "release_fallback_smoke.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
CONFIG = (ROOT / "config.py").read_text(encoding="utf-8")


def test_rel05_keeps_current_default_legacy_until_cutover() -> None:
    assert '"%VENV_PY%" app_entry.py' in RUN_DEFAULT
    assert "app_qt.py" not in RUN_DEFAULT


def test_explicit_legacy_fallback_is_independent_and_forwards_smoke_args() -> None:
    assert '"%VENV_PY%" app_entry.py %*' in RUN_LEGACY
    assert "app_qt.py" not in RUN_LEGACY
    assert "run_app.bat" not in RUN_LEGACY
    assert '"%VENV_PY%" app_qt.py' in RUN_QT
    assert "app_entry.py" not in RUN_QT


def test_fallback_smoke_uses_legacy_storage_only() -> None:
    assert '["cmd", "/d", "/c", "run_legacy.bat", "--release-smoke"]' in FALLBACK_SMOKE
    assert 'profile / "NemexiaRaidManager" / "nemexia.sqlite3"' in FALLBACK_SMOKE
    assert 'profile / "NemexiaRaidManagerV2"' in FALLBACK_SMOKE
    assert "assert not v2_root.exists()" in FALLBACK_SMOKE
    assert 'base = root / "NemexiaRaidManager"' in CONFIG
    assert 'DB_PATH = DATA_DIR / "nemexia.sqlite3"' in CONFIG


def test_windows_release_job_executes_fallback_after_real_install() -> None:
    assert "Run explicit legacy fallback smoke" in WORKFLOW
    assert r"run: .venv\Scripts\python.exe ci\release_fallback_smoke.py" in WORKFLOW


def test_rollback_refs_remain_documented_as_immutable_release_anchors() -> None:
    state = (ROOT / "docs" / "v2-current-state.md").read_text(encoding="utf-8")
    assert "stable/tkinter-v1" in state
    assert "archive/pre-pyside6-4e01bfda" in state
    assert "4e01bfda752c6383e48c0f6eb8be64d68676da67" in state
