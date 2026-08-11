from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from v2.application.browser_identity import (
    AccountContext,
    BrowserIdentitySnapshot,
    BrowserSession,
    PlanetIdentity,
)
from v2.application.navigation import NavigationObservation, NavigationPageState
from v2.application.rest_mode import RestModeObservation, RestModeService
from v2.persistence.database import V2Database
from v2.persistence.rest_mode import (
    REST_MODE_ATTACK_UNVERIFIED,
    RestModeRepository,
    RestModeState,
)


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _observation(*, fingerprint: str = "account-a", planet_id: str = "17", coord: str = "3:39:11"):
    host = "game.ares.nemexia.com"
    planet = PlanetIdentity(
        planet_id=planet_id,
        coord=coord,
        display_name="Home",
        selected=True,
        selected_proof="#planetSwitch",
        server_host=host,
        account_fingerprint=fingerprint,
        ownership_evidence="owned",
    )
    identity = BrowserIdentitySnapshot(
        session=BrowserSession(
            endpoint="http://127.0.0.1:9222",
            page_url=f"https://{host}/fleets.php",
            server_host=host,
            page_count=1,
            game_page_count=1,
            evidence="fake",
        ),
        account=AccountContext(
            server_host=host,
            ownership_fingerprint=fingerprint,
            planet_ids=(planet_id,),
            planet_coords=(coord,),
            evidence="fake",
        ),
        planets=(planet,),
        current_planet=planet,
    )
    return NavigationObservation(
        "page-1",
        identity,
        NavigationPageState(page_kind="fleets", fleets_ready=True),
    )


class FakeNavigation:
    def __init__(self, observations=None, unresolved=()) -> None:
        self.observations = list(observations or [])
        self.default = _observation()
        self._unresolved = tuple(unresolved)
        self.observe_calls = 0

    def unresolved(self):
        return self._unresolved

    def observe(self):
        self.observe_calls += 1
        if self.observations:
            value = self.observations.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return self.default


class FakeReadiness:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    def ensure_fleets(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return object()


class FakeBrowser:
    def __init__(self, minutes=60) -> None:
        self.values = list(minutes if isinstance(minutes, (tuple, list)) else (minutes,))
        self.calls = 0

    def read_rest_mode_observation(self, **_kwargs):
        self.calls += 1
        value = self.values.pop(0) if self.values else 60
        if isinstance(value, Exception):
            raise value
        if isinstance(value, RestModeObservation):
            return value
        return RestModeObservation(NOW.isoformat(), int(value), detail=f"{value} min")


class ThreadSafeRestModeRepositoryDouble:
    """Concurrency-only state double; deliberately not a SQLite owner.

    Real RestModeRepository/V2Database tests stay on the creating test thread.
    This double lets lock/stop ordering be exercised with actual RestModeService
    without transferring a sqlite3.Connection across worker threads.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.current = RestModeState(
            armed=False,
            status="DISARMED",
            session_id="",
            server_host="",
            account_fingerprint="",
            planet_id="",
            planet_coord="",
            started_at=None,
            last_success_at=None,
            next_check_at=None,
            last_activity_minutes=None,
            activity_epoch=0,
            activity_warning_sent=False,
            attack_watch_state=REST_MODE_ATTACK_UNVERIFIED,
            last_error="",
            blocking_navigation_request_id="",
            detail="",
            updated_at=NOW.isoformat(),
        )

    def _set(self, **changes) -> RestModeState:
        self.current = replace(self.current, updated_at=NOW.isoformat(), **changes)
        return self.current

    def read(self) -> RestModeState:
        with self._lock:
            return self.current

    def disarm_on_startup(self) -> RestModeState:
        with self._lock:
            if not self.current.armed and self.current.status == "DISARMED":
                return self.current
            return self._set(armed=False, status="DISARMED", next_check_at=None)

    def begin_start(
        self,
        *,
        session_id: str,
        server_host: str,
        account_fingerprint: str,
        planet_id: str,
        planet_coord: str,
        started_at: str,
    ) -> RestModeState:
        with self._lock:
            same_identity = (
                self.current.server_host == server_host
                and self.current.account_fingerprint == account_fingerprint
                and self.current.planet_id == planet_id
                and self.current.planet_coord == planet_coord
            )
            return self._set(
                armed=False,
                status="STARTING",
                session_id=session_id,
                server_host=server_host,
                account_fingerprint=account_fingerprint,
                planet_id=planet_id,
                planet_coord=planet_coord,
                started_at=started_at,
                next_check_at=None,
                activity_epoch=self.current.activity_epoch if same_identity else 0,
                activity_warning_sent=(self.current.activity_warning_sent if same_identity else False),
                attack_watch_state=REST_MODE_ATTACK_UNVERIFIED,
                last_error="",
                blocking_navigation_request_id="",
                detail="",
            )

    def save_observation(
        self,
        *,
        status: str,
        armed: bool,
        activity_minutes: int,
        activity_epoch: int,
        warning_sent: bool,
        observed_at: str,
        next_check_at: str | None,
        detail: str = "",
    ) -> RestModeState:
        with self._lock:
            return self._set(
                armed=armed,
                status=status,
                last_success_at=observed_at,
                next_check_at=next_check_at,
                last_activity_minutes=activity_minutes,
                activity_epoch=activity_epoch,
                activity_warning_sent=warning_sent,
                attack_watch_state=REST_MODE_ATTACK_UNVERIFIED,
                last_error="",
                blocking_navigation_request_id="",
                detail=detail,
            )

    def block(
        self,
        *,
        status: str,
        detail: str,
        blocking_navigation_request_id: str = "",
    ) -> RestModeState:
        with self._lock:
            return self._set(
                armed=False,
                status=status,
                next_check_at=None,
                last_error=detail,
                blocking_navigation_request_id=blocking_navigation_request_id,
                detail=detail,
            )

    def stop(self, *, detail: str = "Stopped by operator") -> RestModeState:
        with self._lock:
            return self._set(
                armed=False,
                status="DISARMED",
                next_check_at=None,
                detail=detail,
            )


def _service(tmp_path, *, navigation=None, readiness=None, browser=None):
    db = V2Database(tmp_path / "v2.sqlite3")
    service = RestModeService(
        repository=RestModeRepository(db),
        navigation=navigation or FakeNavigation(),
        readiness=readiness or FakeReadiness(),
        browser=browser or FakeBrowser(),
    )
    return db, service


def test_explicit_start_arms_and_first_low_sample_warns_once(tmp_path) -> None:
    browser = FakeBrowser((20, 15, 60, 20))
    db, service = _service(tmp_path, browser=browser)

    first = service.start(now=NOW)
    assert first.state.armed is True
    assert first.state.status == "ACTIVITY_WARNING"
    assert first.warning_emitted is True
    assert first.state.activity_warning_sent is True

    repeated = service.tick(now=NOW, force=True)
    assert repeated.warning_emitted is False
    assert repeated.state.activity_epoch == first.state.activity_epoch

    reset = service.tick(now=NOW, force=True)
    assert reset.warning_emitted is False
    assert reset.state.status == "WATCHING"
    assert reset.state.activity_warning_sent is False
    assert reset.state.activity_epoch == first.state.activity_epoch + 1

    next_low = service.tick(now=NOW, force=True)
    assert next_low.warning_emitted is True
    assert next_low.state.activity_warning_sent is True
    assert next_low.state.activity_epoch == reset.state.activity_epoch
    db.close()


def test_unresolved_navigation_blocks_before_any_browser_work(tmp_path) -> None:
    unresolved = SimpleNamespace(request_id="nav-ambiguous-1", status="ambiguous")
    navigation = FakeNavigation(unresolved=(unresolved,))
    readiness = FakeReadiness()
    browser = FakeBrowser()
    db, service = _service(
        tmp_path,
        navigation=navigation,
        readiness=readiness,
        browser=browser,
    )

    result = service.start(now=NOW)
    assert result.state.armed is False
    assert result.state.status == "BLOCKED_AMBIGUOUS"
    assert result.state.blocking_navigation_request_id == "nav-ambiguous-1"
    assert navigation.observe_calls == 0
    assert readiness.calls == 0
    assert browser.calls == 0
    db.close()


def test_identity_drift_blocks_before_reader(tmp_path) -> None:
    navigation = FakeNavigation(
        observations=(
            _observation(),
            _observation(),
            _observation(fingerprint="account-b"),
        )
    )
    browser = FakeBrowser()
    db, service = _service(tmp_path, navigation=navigation, browser=browser)

    result = service.start(now=NOW)
    assert result.state.armed is False
    assert result.state.status == "BLOCKED_IDENTITY"
    assert browser.calls == 0
    db.close()


def test_captcha_observation_stops_without_retry(tmp_path) -> None:
    captcha = RestModeObservation(
        NOW.isoformat(),
        0,
        captcha_required=True,
        detail="CAPTCHA / bot-check detected",
    )
    browser = FakeBrowser((captcha,))
    db, service = _service(tmp_path, browser=browser)

    result = service.start(now=NOW)
    assert result.state.armed is False
    assert result.state.status == "CAPTCHA_REQUIRED"
    assert browser.calls == 1
    assert service.tick(now=NOW, force=True).state.status == "CAPTCHA_REQUIRED"
    assert browser.calls == 1
    db.close()


def test_bound_browser_loss_is_blocked_browser(tmp_path) -> None:
    navigation = FakeNavigation(
        observations=(RuntimeError("Mutation CDP session was lost; explicit recovery is required"),)
    )
    db, service = _service(tmp_path, navigation=navigation)
    result = service.start(now=NOW)
    assert result.state.armed is False
    assert result.state.status == "BLOCKED_BROWSER"
    db.close()


def test_stop_intent_blocks_queued_tick_and_drains_active_cycle_without_sqlite_cross_thread() -> None:
    entered = threading.Event()
    release = threading.Event()
    tick_b_started = threading.Event()

    class BlockingBrowser(FakeBrowser):
        def __init__(self):
            super().__init__((60,))
            self.block_next = False

        def read_rest_mode_observation(self, **_kwargs):
            self.calls += 1
            if self.block_next:
                entered.set()
                assert release.wait(timeout=3)
                return RestModeObservation(NOW.isoformat(), 55, detail="55 min")
            value = self.values.pop(0) if self.values else 60
            return RestModeObservation(NOW.isoformat(), int(value), detail=f"{value} min")

    browser = BlockingBrowser()
    repository = ThreadSafeRestModeRepositoryDouble()
    service = RestModeService(
        repository=repository,
        navigation=FakeNavigation(),
        readiness=FakeReadiness(),
        browser=browser,
    )
    assert service.start(now=NOW).state.armed is True
    assert browser.calls == 1
    browser.block_next = True

    tick_results = []
    tick_a = threading.Thread(
        target=lambda: tick_results.append(("A", service.tick(now=NOW, force=True)))
    )
    tick_a.start()
    assert entered.wait(timeout=2)

    def run_tick_b() -> None:
        tick_b_started.set()
        tick_results.append(("B", service.tick(now=NOW, force=True)))

    tick_b = threading.Thread(target=run_tick_b)
    tick_b.start()
    assert tick_b_started.wait(timeout=2)

    stopped = []
    stop_thread = threading.Thread(target=lambda: stopped.append(service.stop()))
    stop_thread.start()
    assert service._stop_requested.wait(timeout=2)
    assert stop_thread.is_alive(), "Stop must wait for active tick A to drain"

    release.set()
    tick_a.join(timeout=3)
    tick_b.join(timeout=3)
    stop_thread.join(timeout=3)

    assert not tick_a.is_alive()
    assert not tick_b.is_alive()
    assert not stop_thread.is_alive()
    assert browser.calls == 2, "queued tick B must perform zero browser work after Stop intent"
    assert stopped and stopped[0].armed is False
    assert stopped[0].status == "DISARMED"
    assert repository.read().armed is False
    assert repository.read().status == "DISARMED"
