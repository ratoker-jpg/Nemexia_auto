from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_qt_bootstrap_wires_one_shared_asteroid_backend_without_ui_trigger() -> None:
    app = text("app_qt.py")
    assert "V2AsteroidCdpBackend" in app
    assert "V2AsteroidSource(asteroid_backend)" in app
    assert "AsteroidActionService(" in app
    assert "AsteroidEnabledApplicationContext(" in app
    assert 'enabled=bool(settings.get("actions_enabled"))' in app
    assert "dispatch_asteroid(" not in app


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
