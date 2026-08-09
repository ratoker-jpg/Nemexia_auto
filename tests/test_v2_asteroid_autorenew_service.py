from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from v2.application.asteroid_actions import AsteroidDispatchResult
from v2.application.asteroid_autorenew import AsteroidAutorenewError, AsteroidAutorenewService
from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.navigation import NavigationObservation, NavigationPageState
from v2.persistence.database import V2Database


SOURCE = "3:39:8"


def observation(*, page_kind: str = "galaxy", galaxy: int = 3, solar: int = 39) -> NavigationObservation:
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url=f"https://game.ares.nemexia.com/{'fleets.php' if page_kind == 'fleets' else 'galaxy.php'}",
        page_count=1,
        game_page_count=1,
        planets=(PlanetDomFact("101", SOURCE, "AST", True),),
        trigger_coord=SOURCE,
    )
    return NavigationObservation(
        "runtime-page:auto11",
        identity,
        NavigationPageState(
            page_kind=page_kind,
            fleets_ready=page_kind == "fleets",
            galaxy_ready=page_kind == "galaxy",
            galaxy=galaxy if page_kind == "galaxy" else None,
            solar=solar if page_kind == "galaxy" else None,
        ),
    )


class FakeNavigation:
    def __init__(self, *, unresolved=()) -> None:
        self.current = observation()
        self.unresolved_rows = tuple(unresolved)
        self.observe_calls = 0
        self.mutation_calls: list[str] = []

    def unresolved(self):
        return self.unresolved_rows

    def observe(self):
        self.observe_calls += 1
        return self.current

    def switch_planet(self, *, request_id: str, planet_id: str):
        self.mutation_calls.append("switch_planet")
        return SimpleNamespace(status="verified", detail="verified")

    def prepare_galaxy(self, *, request_id: str):
        self.mutation_calls.append("prepare_galaxy")
        self.current = observation(page_kind="galaxy")
        return SimpleNamespace(status="verified", detail="verified")

    def prepare_fleets(self, *, request_id: str):
        self.mutation_calls.append("prepare_fleets")
        self.current = observation(page_kind="fleets")
        return SimpleNamespace(status="verified", detail="verified")

    def navigate_galaxy_system(self, *, request_id: str, galaxy: int, solar: int):
        self.mutation_calls.append(f"system:{galaxy}:{solar}")
        self.current = observation(page_kind="galaxy", galaxy=galaxy, solar=solar)
        return SimpleNamespace(status="verified", detail="verified")


class FakeDiscoveryRepository:
    def read(self, _scan_id: str):
        return None


class FakeAsteroidStorage:
    def identities(self):
        return set()


class FakeDiscovery:
    def __init__(self) -> None:
        self.repository = FakeDiscoveryRepository()
        self.asteroid_storage = FakeAsteroidStorage()


class FakeAsteroidRepository:
    def observations(self):
        return ()


class FakeCaptchaProbe:
    def __init__(self, present: bool = False) -> None:
        self.present = present
        self.calls = 0

    def autorenew_captcha_present(self) -> bool:
        self.calls += 1
        return self.present


class FakeActions:
    enabled = True


class FakeDiscoveryBrowser:
    pass


def service(tmp_path: Path, *, navigation: FakeNavigation | None = None, captcha: FakeCaptchaProbe | None = None):
    database = V2Database(tmp_path / "v2.sqlite3")
    nav = navigation or FakeNavigation()
    svc = AsteroidAutorenewService(
        database=database,
        navigation=nav,
        discovery=FakeDiscovery(),  # type: ignore[arg-type]
        discovery_browser=FakeDiscoveryBrowser(),  # type: ignore[arg-type]
        asteroid_repository=FakeAsteroidRepository(),  # type: ignore[arg-type]
        asteroid_actions=FakeActions(),  # type: ignore[arg-type]
        captcha_probe=captcha or FakeCaptchaProbe(),
        request_id=lambda: "fixed",
    )
    return database, nav, svc


def test_start_blocks_unresolved_navigation_before_any_observe_or_readiness_mutation(tmp_path: Path) -> None:
    unresolved = SimpleNamespace(request_id="nav-pending", status="ambiguous")
    nav = FakeNavigation(unresolved=(unresolved,))
    database, nav, svc = service(tmp_path, navigation=nav)
    with pytest.raises(AsteroidAutorenewError, match="unresolved navigation"):
        svc.start(source=SOURCE, start_immediately=True)
    assert nav.observe_calls == 0
    assert nav.mutation_calls == []
    assert svc.state().armed is False
    database.close()


def test_explicit_stop_prevents_future_due_tick_mutations(tmp_path: Path) -> None:
    database, nav, svc = service(tmp_path)
    armed = svc.start(source=SOURCE, start_immediately=False)
    assert armed.state.armed is True
    before = list(nav.mutation_calls)
    stopped = svc.stop()
    assert stopped.armed is False
    tick = svc.tick(force=True)
    assert tick.state.armed is False
    assert nav.mutation_calls == before
    database.close()


def test_waiting_captcha_is_hard_stop_and_never_auto_resumes(tmp_path: Path) -> None:
    captcha = FakeCaptchaProbe(True)
    database, _, svc = service(tmp_path, captcha=captcha)
    svc.start(source=SOURCE, start_immediately=False)
    svc.repository.transition(
        status="waiting_return",
        armed=True,
        next_cycle_at="2026-08-10T10:00:00+00:00",
        last_return_at="2026-08-10T09:55:00+00:00",
        verified_sent=1,
        detail="waiting",
    )
    tick = svc.tick(now=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc))
    assert captcha.calls == 1
    assert tick.state.armed is False
    assert tick.state.status == "stopped_captcha"
    database.close()


def test_next_cycle_uses_latest_verified_return_plus_buffer(tmp_path: Path) -> None:
    database, _, svc = service(tmp_path)
    svc.start(source=SOURCE, buffer_minutes=5, start_immediately=False)
    state = svc.state()
    base = datetime(2026, 8, 9, 20, 0, tzinfo=timezone.utc)
    svc._cycle_results = {
        "one": AsteroidDispatchResult(
            source=SOURCE,
            observation_coord="3:20:4",
            target="3:20:4",
            recycler_count=5,
            sent_at=base,
            arrival_at=base + timedelta(minutes=5),
            return_at=base + timedelta(minutes=10),
            fleet_id="101",
            verified=True,
        ),
        "two": AsteroidDispatchResult(
            source=SOURCE,
            observation_coord="3:19:4",
            target="3:19:4",
            recycler_count=5,
            sent_at=base,
            arrival_at=base + timedelta(minutes=8),
            return_at=base + timedelta(minutes=20),
            fleet_id="102",
            verified=True,
        ),
    }
    tick = svc._schedule_after_verified(state)
    assert tick.state.status == "waiting_return"
    assert tick.state.armed is True
    assert tick.state.due_at == base + timedelta(minutes=25)
    assert tick.state.verified_sent == 2
    database.close()


def test_existing_verified_candidate_request_is_recovered_without_second_dispatch(tmp_path: Path) -> None:
    database, _, svc = service(tmp_path)
    svc.start(source=SOURCE, start_immediately=False)
    state = svc.repository.transition(
        status="running_dispatch",
        armed=True,
        active_scan_id="scan-1",
        cycle_started_at="2026-08-09T20:00:00+00:00",
        verified_sent=0,
        detail="dispatch",
    )
    svc._cycle_candidates = (object(),)  # existing record is checked before candidate browser work
    record = SimpleNamespace(
        status="verified",
        return_at="2026-08-09T20:20:00+00:00",
        sent_at="2026-08-09T20:00:00+00:00",
        arrival_at="2026-08-09T20:10:00+00:00",
        source=SOURCE,
        observation_coord="3:20:4",
        target="3:20:4",
        recycler_count=5,
        fleet_id="123",
        detail="verified",
    )

    class Coordinator:
        dispatch_calls = 0

        def record(self, _request_id: str):
            return record

        def dispatch(self, *_args, **_kwargs):
            self.dispatch_calls += 1
            raise AssertionError("verified immutable request must not be dispatched twice")

    coordinator = Coordinator()
    svc.coordinator = coordinator  # type: ignore[assignment]
    tick = svc._dispatch_tick(state, datetime(2026, 8, 9, 20, 1, tzinfo=timezone.utc))
    assert coordinator.dispatch_calls == 0
    assert tick.remote_send_attempted is False
    assert tick.verified_send is True
    assert tick.state.verified_sent == 1
    database.close()
