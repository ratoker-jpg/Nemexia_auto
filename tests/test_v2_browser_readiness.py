from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.browser_readiness import (
    BrowserReadinessError,
    BrowserReadinessManager,
    ReadinessState,
)
from v2.application.navigation import NavigationObservation, NavigationPageState
from v2.infrastructure.cdp_mutation_sessions import _NoAutoReconnectMixin


def _identity(selected: str = "101"):
    coord = "3:39:11" if selected == "101" else "3:39:8"
    return build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url="https://game.ares.nemexia.com/overview.php",
        page_count=1,
        game_page_count=1,
        planets=(
            PlanetDomFact("101", "3:39:11", "HOME", selected == "101"),
            PlanetDomFact("202", "3:39:8", "GAS", selected == "202"),
        ),
        trigger_coord=coord,
    )


def _observation(kind: str = "other", selected: str = "101") -> NavigationObservation:
    return NavigationObservation(
        "runtime-page:6",
        _identity(selected),
        NavigationPageState(
            page_kind=kind,
            fleets_ready=kind == "fleets",
            options_ready=kind in {"options", "messages"},
            messages_ready=kind == "messages",
            galaxy_ready=kind == "galaxy",
            galaxy=3 if kind == "galaxy" else None,
            solar=39 if kind == "galaxy" else None,
        ),
    )


class _Navigation:
    def __init__(self) -> None:
        self.current = _observation()
        self.calls: list[tuple[str, str]] = []

    def observe(self):
        return self.current

    def switch_planet(self, *, request_id: str, planet_id: str):
        self.calls.append(("planet", request_id))
        self.current = _observation("other", selected=planet_id)
        return SimpleNamespace(status="verified", detail="planet ready")

    def prepare_fleets(self, *, request_id: str):
        self.calls.append(("fleets", request_id))
        selected = self.current.identity.current_planet.planet_id
        self.current = _observation("fleets", selected=selected)
        return SimpleNamespace(status="verified", detail="fleets ready")

    def prepare_galaxy(self, *, request_id: str):
        self.calls.append(("galaxy", request_id))
        selected = self.current.identity.current_planet.planet_id
        self.current = _observation("galaxy", selected=selected)
        return SimpleNamespace(status="verified", detail="galaxy ready")

    def prepare_system_messages(self, *, request_id: str):
        self.calls.append(("messages", request_id))
        selected = self.current.identity.current_planet.planet_id
        self.current = _observation("messages", selected=selected)
        return SimpleNamespace(verified=True)


def test_snapshot_is_human_readable_and_componentized() -> None:
    manager = BrowserReadinessManager(_Navigation())
    snapshot = manager.snapshot()

    assert snapshot.browser.ready is True
    assert snapshot.account.ready is True
    assert snapshot.planet.ready is True
    assert snapshot.fleets.state is ReadinessState.NOT_READY
    assert snapshot.messages.state is ReadinessState.NOT_READY
    assert snapshot.galaxy.state is ReadinessState.NOT_READY
    assert [item.label for item in snapshot.items()] == [
        "Browser", "Account", "Planet", "Fleets", "Messages", "Galaxy"
    ]


def test_ensure_fleets_switches_only_to_proven_owned_planet_then_prepares_page() -> None:
    navigation = _Navigation()
    manager = BrowserReadinessManager(navigation)

    snapshot = manager.ensure_fleets(planet_coord="3:39:8")

    assert snapshot.planet.ready is True
    assert "3:39:8" in snapshot.planet.detail
    assert snapshot.fleets.ready is True
    assert [call[0] for call in navigation.calls] == ["planet", "fleets"]
    assert all(call[1].startswith("readiness:") for call in navigation.calls)
    assert len({call[1] for call in navigation.calls}) == 2


def test_ensure_messages_and_galaxy_prepare_normal_recoverable_state() -> None:
    navigation = _Navigation()
    manager = BrowserReadinessManager(navigation)

    messages = manager.ensure_messages()
    assert messages.messages.ready is True
    assert navigation.calls[-1][0] == "messages"

    galaxy = manager.ensure_galaxy()
    assert galaxy.galaxy.ready is True
    assert navigation.calls[-1][0] == "galaxy"


def test_unowned_planet_is_blocked_before_navigation() -> None:
    navigation = _Navigation()
    manager = BrowserReadinessManager(navigation)

    with pytest.raises(BrowserReadinessError, match="not in the proven owned-planet set"):
        manager.ensure_fleets(planet_coord="1:1:1")
    assert navigation.calls == []


def test_captcha_is_a_global_stop_state() -> None:
    class CaptchaNavigation:
        def observe(self):
            raise RuntimeError("CAPTCHA обнаружена")

    snapshot = BrowserReadinessManager(CaptchaNavigation()).snapshot()
    assert snapshot.captcha_stopped is True
    assert all(item.state is ReadinessState.STOPPED for item in snapshot.items())


class _Browser:
    def __init__(self) -> None:
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected


class _BaseBackend:
    def __init__(self) -> None:
        self._browser = None
        self.attach_calls = 0

    async def _ensure_browser(self):
        self.attach_calls += 1
        self._browser = _Browser()
        return self._browser


class _MutationBackend(_NoAutoReconnectMixin, _BaseBackend):
    pass


def test_mutation_session_initial_attach_is_allowed_but_silent_reconnect_is_not() -> None:
    backend = _MutationBackend()
    first = asyncio.run(backend._ensure_browser())
    assert first.is_connected() is True
    assert backend.attach_calls == 1

    first.connected = False
    with pytest.raises(RuntimeError, match="auto_reconnect=False"):
        asyncio.run(backend._ensure_browser())
    assert backend.attach_calls == 1


def test_auto06_application_layer_contains_no_browser_selectors() -> None:
    root = Path(__file__).resolve().parents[1]
    manager = (root / "v2" / "application" / "browser_readiness.py").read_text(encoding="utf-8")
    context = (root / "v2" / "application" / "automation_context.py").read_text(encoding="utf-8")
    app = (root / "app_qt.py").read_text(encoding="utf-8")

    for forbidden in ("playwright", "#planetSwitch", "#FleetsCount", "loadTabContent", "refreshGalaxy"):
        assert forbidden not in manager
        assert forbidden not in context
    for safe_backend in (
        "V2NavigationCdpBackendNoAutoReconnect",
        "V2RaidCdpBackendNoAutoReconnect",
        "V2SpyCdpBackendNoAutoReconnect",
        "V2AsteroidCdpBackendNoAutoReconnect",
    ):
        assert safe_backend in app
