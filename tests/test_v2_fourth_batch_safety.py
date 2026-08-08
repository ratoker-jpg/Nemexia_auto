from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAVED_FLEETS = ROOT / "saved_pages" / "2026-08-08_08-54-11-072" / "page.html"
CDP = (ROOT / "v2" / "infrastructure" / "cdp_read_backend.py").read_text(encoding="utf-8")
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
ACTIVE = (ROOT / "v2" / "ui" / "pages" / "active.py").read_text(encoding="utf-8")
LEGACY_RUNNER = (ROOT / "run_app.bat").read_text(encoding="utf-8")


def test_v2_capacity_selectors_are_grounded_in_saved_real_fleets_page() -> None:
    html = SAVED_FLEETS.read_text(encoding="utf-8")
    assert 'id="FleetsCount">20<' in html
    assert 'id="MaxFleets">22<' in html
    assert "#FleetsCount" in CDP
    assert "#MaxFleets" in CDP


def test_concrete_qt_browser_path_stays_attach_only_and_read_only() -> None:
    assert "ReadOnlyCdpBackend" in APP_QT
    assert "connect_over_cdp" in CDP
    assert "fleets.php" in CDP
    assert "#fleetHandler tbody tr" in CDP
    assert "refresh_live_source()" in ACTIVE

    combined = APP_QT + CDP + ACTIVE
    for forbidden in (
        "BrowserWorker",
        "launch_yandex",
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "showFleets()",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "bring_to_front(",
    ):
        assert forbidden not in combined


def test_legacy_runtime_is_not_switched_to_qt() -> None:
    assert '"%VENV_PY%" app_entry.py' in LEGACY_RUNNER
    assert "app_qt.py" not in LEGACY_RUNNER
