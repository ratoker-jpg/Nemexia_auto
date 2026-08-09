from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "v2" / "ui" / "browser_readiness_panel.py").read_text(encoding="utf-8")
MAIN = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
THEME = (ROOT / "v2" / "ui" / "theme.py").read_text(encoding="utf-8")


def test_main_shell_surfaces_all_six_browser_readiness_components() -> None:
    assert "BrowserReadinessPanel(self.context" in MAIN
    for label in ("Browser", "Account", "Planet", "Fleets", "Messages", "Galaxy"):
        assert f'"{label}"' in PANEL
    assert "refresh_async" in PANEL
    assert "QThreadPool.globalInstance()" in PANEL
    assert "QTimer.singleShot(0, self.refresh_async)" in PANEL


def test_readiness_ui_only_calls_application_service_and_has_no_browser_selectors() -> None:
    assert 'getattr(self.context, "browser_readiness", None)' in PANEL
    for forbidden in (
        "playwright",
        "connect_over_cdp",
        "#planetSwitch",
        "#planetsListHolder",
        "#FleetsCount",
        "loadTabContent",
        "refreshGalaxy",
        "processSpy",
        "SendFleet",
    ):
        assert forbidden not in PANEL
        assert forbidden not in MAIN


def test_readiness_presentation_distinguishes_ready_blocked_and_stopped() -> None:
    assert 'if state == "ready"' in PANEL
    assert 'if state == "stopped"' in PANEL
    assert 'if state == "blocked"' in PANEL
    assert '"success"' in PANEL
    assert '"danger"' in PANEL
    assert '"warning"' in PANEL
    assert "captcha" in PANEL.casefold()


def test_ui_copy_no_longer_describes_v2_as_attach_only() -> None:
    assert "ATTACH-ONLY" not in MAIN
    assert "AUTOMATION · JOURNALED SAFETY" in MAIN
    assert "V2 · AUTOMATION" in MAIN
    assert "BrowserReadinessBar" in THEME
