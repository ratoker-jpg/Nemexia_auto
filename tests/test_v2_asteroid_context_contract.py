from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_qt_bootstrap_wires_one_shared_asteroid_backend_without_ui_trigger() -> None:
    app = text("app_qt.py")
    debris_context = text("v2/application/debris_context.py")
    autorenew_backend = text("v2/infrastructure/cdp_asteroid_autorenew_backend.py")
    autorenew_context = text("v2/application/asteroid_autorenew_context.py")
    rest_context = text("v2/application/rest_mode_context.py")
    assert "V2AutorenewAsteroidCdpBackendNoAutoReconnect" in app
    assert app.count("V2AutorenewAsteroidCdpBackendNoAutoReconnect(endpoint.endpoint)") == 1
    assert "V2AsteroidCdpBackendNoAutoReconnect" in autorenew_backend
    assert "V2AsteroidSource(asteroid_backend)" in app
    assert "AsteroidActionService(" in app
    assert "RestModeApplicationContext(" in app
    assert "class RestModeApplicationContext(AsteroidAutorenewApplicationContext)" in rest_context
    assert "class AsteroidAutorenewApplicationContext(DebrisEnabledApplicationContextWithReadiness)" in autorenew_context
    assert "class DebrisEnabledApplicationContext(AsteroidEnabledApplicationContext)" in debris_context
    assert "AsteroidRequestCoordinator(self._asteroid_actions, database)" in debris_context
    assert 'enabled=bool(settings.get("actions_enabled"))' in app
    assert "dispatch_asteroid(" not in app
    assert '"debris_actions"' not in debris_context


def test_context_exposes_only_explicit_journaled_manual_dispatch() -> None:
    context = text("v2/application/asteroid_context.py")
    assert "AsteroidRequestCoordinator" in context
    assert "request_id" in context
    assert "def prepare_asteroid(" in context
    assert "def dispatch_asteroid(" in context
    assert "def recent_asteroid_actions(" in context
    assert "_asteroid_actions.set_enabled" in context
    for forbidden in ("QTimer", "scheduler", "auto_repeat", "after(", "processEvents"):
        assert forbidden not in context
