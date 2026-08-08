from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_main_window_uses_real_debris_page_not_placeholder() -> None:
    source = text("v2/ui/main_window.py")
    assert "from v2.ui.pages.debris import DebrisPage" in source
    assert 'if key == "debris":\n            return DebrisPage(self.context, self)' in source


def test_debris_page_calls_only_application_context_surfaces() -> None:
    source = text("v2/ui/pages/debris.py")
    for required in (
        'getattr(self.context, "live_debris"',
        'getattr(self.context, "ingest_debris_read"',
        'getattr(self.context, "prepare_debris_candidates"',
        'getattr(self.context, "confirm_debris_candidates"',
        'getattr(self.context, "request_debris_stop"',
        "DebrisReadState.CAPTCHA",
        "DebrisReadState.LIVE_UNAVAILABLE",
        "DebrisReadState.PARTIAL_EVIDENCE",
        "DebrisReadState.NO_DEBRIS",
        "DebrisWorkflowState.STOPPED_MANUAL",
        "result.state.value",
    ):
        assert required in source
    for forbidden in (
        "playwright",
        "ReadOnlyDebrisCdpBackend",
        "V2AsteroidCdpBackend",
        "SendFleetButton",
        "refreshGalaxy",
        ".goto(",
        "new_page(",
        "ajax_galaxy.php",
    ):
        assert forbidden not in source
    assert "автоматический обход 3×40" in source
    assert "Прочитать открытую систему" in source


def test_debris_context_reuses_same_asteroid_action_service_and_journal() -> None:
    source = text("v2/application/debris_context.py")
    assert "AsteroidRequestCoordinator(self._asteroid_actions, database)" in source
    assert "DebrisDispatchReuseGate(coordinator)" in source
    assert "DebrisWorkflowController(self._debris_gate)" in source
    assert "debris_actions" not in source


def test_qt_bootstrap_wires_attach_only_debris_reader_without_launcher_cutover() -> None:
    source = text("app_qt.py")
    assert "ReadOnlyDebrisCdpBackend(endpoint.endpoint)" in source
    assert "V2DebrisSource" in source
    assert "DebrisEnabledApplicationContext" in source

    launcher = text("run_app.bat")
    assert "app_entry.py" in launcher
    assert "app_qt.py" not in launcher
