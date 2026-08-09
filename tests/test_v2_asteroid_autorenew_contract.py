from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "v2/application/asteroid_autorenew.py").read_text(encoding="utf-8")
CONTEXT = (ROOT / "v2/application/asteroid_autorenew_context.py").read_text(encoding="utf-8")
BACKEND = (ROOT / "v2/infrastructure/cdp_asteroid_autorenew_backend.py").read_text(encoding="utf-8")
APP = (ROOT / "app_qt.py").read_text(encoding="utf-8")
AUDIT = (ROOT / "docs/audits/2026-08-09-v2-auto11-asteroid-autorenew-audit.md").read_text(
    encoding="utf-8"
)


def test_auto11_reuses_existing_asteroid_sendfleet_implementation() -> None:
    assert "V2AsteroidCdpBackendNoAutoReconnect" in BACKEND
    assert "_matching_galaxy_page" in BACKEND
    for forbidden in ("SendFleetButton", ".click(", "type=SendFleet", "ajax_fleets.php"):
        assert forbidden not in BACKEND
    assert "V2AutorenewAsteroidCdpBackendNoAutoReconnect" in APP


def test_scheduler_has_no_browser_or_qt_implementation_details() -> None:
    for forbidden in (
        "playwright",
        "PySide6",
        "document.querySelector",
        "#FleetsCount",
        "#MaxFleets",
        "#ship_1_11",
        "ajax_info.php",
        "SendFleetButton",
    ):
        assert forbidden not in SERVICE
        assert forbidden not in CONTEXT


def test_auto11_is_asteroid_only_and_does_not_invent_debris_repeat() -> None:
    assert "debris" not in SERVICE.casefold()
    assert "No debris autorenew/repeat" in AUDIT
    assert "No common \"repeat everything\" scheduler" in AUDIT


def test_typed_context_exposes_explicit_start_stop_tick_and_status() -> None:
    for token in (
        "asteroid_autorenew_state",
        "start_asteroid_autorenew",
        "stop_asteroid_autorenew",
        "tick_asteroid_autorenew",
    ):
        assert token in CONTEXT
    assert "start_immediately" in CONTEXT


def test_restart_disarm_and_unresolved_gates_are_source_locked() -> None:
    assert "disarm_on_startup" in SERVICE
    assert "_require_navigation_clear()" in SERVICE
    assert "_require_action_clear()" in SERVICE
    assert "account_fingerprint" in SERVICE
    assert "source_planet_id" in SERVICE
    assert "latest" in AUDIT.casefold() and "return_at" in AUDIT
