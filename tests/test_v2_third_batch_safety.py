from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "v2" / "ui" / "pages"
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
DIAGNOSTICS = (PAGES / "diagnostics.py").read_text(encoding="utf-8")
LEGACY_RUNNER = (ROOT / "run_app.bat").read_text(encoding="utf-8")


def test_third_batch_pages_are_real_and_diagnostics_exposes_source_truth() -> None:
    for key, page in (
        ("plan", "PlanPage"),
        ("active", "ActivePage"),
        ("recon", "ReconPage"),
    ):
        assert f'if key == "{key}"' in MAIN
        assert page in MAIN
    assert "context.cached_flight_status()" in DIAGNOSTICS
    assert "context.flight_status()" not in DIAGNOSTICS
    assert "Live-полёты" in DIAGNOSTICS


def test_active_and_recon_remain_action_free() -> None:
    combined = "\n".join(
        (PAGES / name).read_text(encoding="utf-8")
        for name in ("active.py", "recon.py")
    )
    for forbidden in (
        "send_raid",
        "prepare_raid",
        "dispatch_plan_raid",
        "request_spy",
        "delete_messages",
        "replace_queue",
        "generate_queue",
        "BrowserWorker",
        "#SendFleetButton",
        "ajax_fleets.php",
    ):
        assert forbidden not in combined


def test_plan_action_page_has_no_direct_browser_or_sql_surface() -> None:
    plan = (PAGES / "plan.py").read_text(encoding="utf-8")
    assert "context.raid_actions_enabled()" in plan
    assert "context.dispatch_plan_raid" in plan
    for forbidden in (
        "BrowserWorker", "playwright", "#SendFleetButton", "ajax_fleets.php",
        "sqlite3", "INSERT INTO", "UPDATE raid_queue", "DELETE FROM",
    ):
        assert forbidden not in plan


def test_legacy_launcher_is_still_the_default() -> None:
    assert '"%VENV_PY%" app_entry.py' in LEGACY_RUNNER
    assert "app_qt.py" not in LEGACY_RUNNER
