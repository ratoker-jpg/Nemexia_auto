from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_docs_match_actual_default_and_rollback_launchers() -> None:
    default = text("run_app.bat")
    fallback = text("run_legacy.bat")
    readme = text("README.md")
    current = text("docs/v2-current-state.md")
    release = text("docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md")

    assert '"%VENV_PY%" app_qt.py %*' in default
    assert "app_entry.py" not in default
    assert '"%VENV_PY%" app_entry.py %*' in fallback
    assert "app_qt.py" not in fallback

    for doc in (readme, current, release):
        assert "run_app.bat -> app_qt.py" in doc
        assert "run_legacy.bat -> app_entry.py" in doc
        assert "run_app.bat -> app_entry.py" not in doc


def test_release_docs_pin_schema_storage_and_legacy_read_only_boundary() -> None:
    current = text("docs/v2-current-state.md")
    readme_ru = text("README_RU.md")
    store = text("v2/application/read_store.py")
    database = text("v2/persistence/database.py")

    assert "V2 SQLite schema version: **9**" in current
    assert "V2 SQLite schema: **9**" in readme_ru
    assert "%LOCALAPPDATA%\\NemexiaRaidManagerV2\\" in current
    assert "mode=ro" in store
    assert "PRAGMA query_only=ON" in store
    assert "V2_SCHEMA_VERSION = 9" in database


def test_release_docs_keep_no_navigation_and_mutation_limitations_explicit() -> None:
    current = text("docs/v2-current-state.md")
    release = text("docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md")
    combined = current + release

    for required in (
        "NO NAVIGATION BOUNDARY",
        "automatic 3×40 traversal",
        "background browser navigation",
        "Rest Mode navigation loops",
        "refreshGalaxy",
        "change_planet.php",
        "page.goto",
        "CAPTCHA",
        "automatic message deletion",
        "automatic retry after ambiguous remote side effect",
        "no exact processable spy fleet",
        "unattended asteroid/debris scheduler",
        "V2-68",
        "V2-69",
        "V2-70",
    ):
        assert required in combined


def test_release_lineage_contains_required_exact_baselines() -> None:
    release = text("docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md")
    for sha in (
        "1077125a59a96274017ad09c9814431bdaeb614e",
        "70cbc13ccde6e0545083341f6c7a5ebbbe70628a",
        "8d9c3c548ed74f6b2b55533489b9834126a65908",
        "54ca45eeffea2da8f4fbebdcbcbe28d8b8dc30c5",
        "fd0992bb8eba2d236ffb867e4a034c2aa15b1153",
        "925d28a8a56436135ea9d134e6a9a52bf2236294",
        "2a21fbc9d97de39fabb2bf658f700b3d57851980",
    ):
        assert sha in release
    assert "POST_MERGE_HANDOFF" in release


def test_rollback_refs_and_original_tk_sha_are_documented() -> None:
    current = text("docs/v2-current-state.md")
    release = text("docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md")
    for doc in (current, release):
        assert "stable/tkinter-v1" in doc
        assert "archive/pre-pyside6-4e01bfda" in doc
        assert "4e01bfda752c6383e48c0f6eb8be64d68676da67" in doc


def test_rel09_noop_cleanup_outcome_is_release_truth() -> None:
    current = text("docs/v2-current-state.md")
    release = text("docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md")
    audit = text("docs/audits/2026-08-09-v2-legacy-reachability-audit.md")
    assert "D. PROVEN DEAD = ∅" in audit
    assert "zero production deletions" in current
    assert "production legacy files deleted: **0**" in release


def test_changelog_declares_v2_2_0_0_without_rewriting_legacy_runtime_version() -> None:
    changelog = text("CHANGELOG.md")
    config = text("config.py")
    assert "## 2.0.0 — 2026-08-09" in changelog
    assert 'APP_VERSION = "1.1.0"' in config
    assert "does not rewrite the fallback runtime" in changelog
