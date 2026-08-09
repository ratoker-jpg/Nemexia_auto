from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "audits" / "v2-legacy-retained-rollback-files.txt"


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def retained_paths() -> list[str]:
    return [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_rel08_authorizes_no_legacy_production_deletion() -> None:
    audit = text("docs/audits/2026-08-09-v2-legacy-reachability-audit.md")
    disposition = text("docs/audits/2026-08-09-v2-rel09-rollback-retention.md")
    assert "D. PROVEN DEAD = ∅" in audit
    assert "NO-OP" in disposition
    assert "zero" in disposition


def test_every_manifested_rollback_path_is_still_present() -> None:
    paths = retained_paths()
    assert paths, "retained rollback manifest must not be empty"
    assert len(paths) == len(set(paths)), "retained rollback manifest contains duplicate paths"
    for relative in paths:
        assert (ROOT / relative).exists(), f"tested rollback dependency removed without a new audit: {relative}"


def test_default_and_rollback_entrypoints_remain_strictly_separate() -> None:
    default = text("run_app.bat")
    fallback = text("run_legacy.bat")
    assert '"%VENV_PY%" app_qt.py %*' in default
    assert "app_entry.py" not in default
    assert '"%VENV_PY%" app_entry.py %*' in fallback
    assert "app_qt.py" not in fallback
    assert "run_app.bat" not in fallback


def test_rollback_setup_and_error_paths_retain_shared_message_script() -> None:
    fallback = text("run_legacy.bat")
    install = text("install.bat")
    assert (ROOT / "launcher_messages.ps1").is_file()
    assert "launcher_messages.ps1" in fallback
    assert "launcher_messages.ps1" in install


def test_packaged_rollback_and_black_box_gate_remain_live() -> None:
    spec = text("NemexiaRaidManagerLegacy.spec")
    builder = text("build_legacy_exe.bat")
    workflow = text(".github/workflows/ci.yml")
    fallback_smoke = text("ci/release_fallback_smoke.py")

    assert "['app_entry.py']" in spec
    assert "name='NemexiaRaidManagerLegacy'" in spec
    assert "NemexiaRaidManagerLegacy.spec" in builder
    assert "Run explicit legacy fallback smoke" in workflow
    assert r"run: .venv\Scripts\python.exe ci\release_fallback_smoke.py" in workflow
    assert '["cmd", "/d", "/c", "run_legacy.bat", "--release-smoke"]' in fallback_smoke


def test_legacy_self_test_remains_a_dual_python_ci_gate() -> None:
    workflow = text(".github/workflows/ci.yml")
    assert 'python-version:\n          - "3.10"\n          - "3.11"' in workflow
    assert "Run legacy self-test" in workflow
    assert "python ci/run_legacy_self_test.py" in workflow
