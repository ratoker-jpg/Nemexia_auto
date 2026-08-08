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


def test_new_read_pages_contain_no_action_surface() -> None:
    combined = "\n".join(
        (PAGES / name).read_text(encoding="utf-8")
        for name in ("plan.py", "active.py", "recon.py")
    )
    for forbidden in (
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "replace_queue",
        "generate_queue",
        "BrowserWorker",
    ):
        assert forbidden not in combined


def test_legacy_launcher_is_still_the_default() -> None:
    assert '"%VENV_PY%" app_entry.py' in LEGACY_RUNNER
    assert "app_qt.py" not in LEGACY_RUNNER
