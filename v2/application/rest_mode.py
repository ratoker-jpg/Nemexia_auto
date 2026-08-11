from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, RLock
from typing import Protocol
from uuid import uuid4

from v2.application.browser_readiness import BrowserReadinessError, BrowserReadinessManager
from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.persistence.rest_mode import RestModeRepository, RestModeState


REST_MODE_CHECK_INTERVAL_MINUTES = 5
REST_MODE_ACTIVITY_WARNING_MINUTES = 25


class RestModeError(RuntimeError):
    pass


class RestModeIdentityError(RestModeError):
    pass


class RestModeReadError(RestModeError):
    pass


@dataclass(frozen=True)
class RestModeObservation:
    observed_at: str
    activity_minutes: int
    captcha_required: bool = False
    detail: str = ""


@dataclass(frozen=True)
class RestModeCycleResult:
    state: RestModeState
    warning_emitted: bool = False


class RestModeBrowser(Protocol):
    def read_rest_mode_observation(
        self,
        *,
        expected_server_host: str,
        expected_account_fingerprint: str,
        expected_planet_id: str,
        expected_coord: str,
    ) -> RestModeObservation:
        ...


@dataclass(frozen=True)
class _IdentityAnchor:
    server_host: str
    account_fingerprint: str
    planet_id: str
    planet_coord: str


class RestModeService:
    """Observation-only AUTO-12 service serialized around one coordinator-owned page.

    Production calls are made by the Qt/application thread that owns the V2 SQLite
    connection. The cycle lock/stop intent protect browser-cycle ordering only; they
    deliberately do not make SQLite transferable across threads.
    """

    def __init__(
        self,
        *,
        repository: RestModeRepository,
        navigation: NavigationCoordinator,
        readiness: BrowserReadinessManager,
        browser: RestModeBrowser,
        interval_minutes: int = REST_MODE_CHECK_INTERVAL_MINUTES,
        warning_minutes: int = REST_MODE_ACTIVITY_WARNING_MINUTES,
    ) -> None:
        self.repository = repository
        self.navigation = navigation
        self.readiness = readiness
        self.browser = browser
        self.interval_minutes = max(1, int(interval_minutes))
        self.warning_minutes = max(1, int(warning_minutes))
        self._cycle_lock = RLock()
        self._stop_requested = Event()
        # Persisted armed state is diagnostic evidence only. Construction never
        # resumes browser work without a fresh explicit Start from the operator.
        self.repository.disarm_on_startup()

    @staticmethod
    def _utc_now(now: datetime | None = None) -> datetime:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    def state(self) -> RestModeState:
        return self.repository.read()

    def _unresolved_navigation(self):
        reader = getattr(self.navigation, "unresolved", None)
        return tuple(reader()) if callable(reader) else ()

    def _require_navigation_clear(self) -> None:
        unresolved = self._unresolved_navigation()
        if not unresolved:
            return
        first = unresolved[0]
        request_id = str(getattr(first, "request_id", "unknown"))
        status = str(getattr(first, "status", "unresolved"))
        raise RestModeError(
            f"Rest Mode blocked by unresolved navigation {request_id} ({status}); "
            "zero new browser mutations attempted"
        )

    @staticmethod
    def _anchor(observation: NavigationObservation) -> _IdentityAnchor:
        identity = observation.identity
        current = identity.current_planet
        if current is None or not current.selected:
            raise RestModeIdentityError("Selected PlanetIdentity is not proven")
        fingerprint = str(identity.account.ownership_fingerprint or "")
        host = str(identity.session.server_host or "")
        if not fingerprint or not host:
            raise RestModeIdentityError("AccountContext ownership is not proven")
        return _IdentityAnchor(
            server_host=host,
            account_fingerprint=fingerprint,
            planet_id=str(current.planet_id),
            planet_coord=str(current.coord),
        )

    @staticmethod
    def _require_same_identity(observation: NavigationObservation, expected: _IdentityAnchor) -> None:
        actual = RestModeService._anchor(observation)
        if actual != expected:
            raise RestModeIdentityError(
                "AccountContext / PlanetIdentity changed while Rest Mode was active; explicit Start required"
            )

    @staticmethod
    def _looks_like_browser_loss(detail: str) -> bool:
        folded = str(detail).casefold()
        return any(
            token in folded
            for token in (
                "browser",
                "cdp",
                "session was lost",
                "session loss",
                "tab closed",
                "bound tab",
                "bound nemexia",
                "привязанная nemexia-вкладка потеряна",
                "привязанная вкладка",
                "вкладку закры",
                "авторизованную nemexia-вкладку",
                "login",
                "logged out",
            )
        )

    def _block_for_exception(self, exc: Exception) -> RestModeState:
        # Any terminal block disarms the current epoch and prevents a queued tick
        # from starting fresh browser work before the application boundary releases
        # Rest Mode authority.
        self._stop_requested.set()
        detail = str(exc) or exc.__class__.__name__
        unresolved = self._unresolved_navigation()
        if unresolved:
            first = unresolved[0]
            return self.repository.block(
                status="BLOCKED_AMBIGUOUS",
                detail=detail,
                blocking_navigation_request_id=str(getattr(first, "request_id", "unknown")),
            )
        folded = detail.casefold()
        if (
            "captcha" in folded
            or "botcheck" in folded
            or "humans only" in folded
            or "защита от автоматических действий" in folded
            or "я не робот" in folded
        ):
            return self.repository.block(status="CAPTCHA_REQUIRED", detail=detail)
        if isinstance(exc, RestModeIdentityError):
            return self.repository.block(status="BLOCKED_IDENTITY", detail=detail)
        if isinstance(exc, BrowserReadinessError) or self._looks_like_browser_loss(detail):
            return self.repository.block(status="BLOCKED_BROWSER", detail=detail)
        if isinstance(exc, RestModeReadError):
            return self.repository.block(status="ERROR", detail=detail)
        return self.repository.block(status="ERROR", detail=detail)

    def _apply_observation(
        self,
        observation: RestModeObservation,
        *,
        now: datetime,
    ) -> RestModeCycleResult:
        if observation.captcha_required:
            self._stop_requested.set()
            state = self.repository.block(
                status="CAPTCHA_REQUIRED",
                detail=observation.detail or "CAPTCHA = STOP",
            )
            return RestModeCycleResult(state)

        activity = int(observation.activity_minutes)
        if activity < 0:
            raise RestModeReadError("Activity timer cannot be negative")

        previous = self.repository.read()
        epoch = previous.activity_epoch
        warned = previous.activity_warning_sent
        previous_minutes = previous.last_activity_minutes

        # A proven jump back above the warning threshold establishes a new
        # activity-check epoch. Stop/restart alone never clears dedupe evidence.
        if activity > self.warning_minutes and (
            warned or (previous_minutes is not None and previous_minutes <= self.warning_minutes)
        ):
            epoch += 1
            warned = False

        warning_emitted = activity <= self.warning_minutes and not warned
        if warning_emitted:
            warned = True

        status = "ACTIVITY_WARNING" if activity <= self.warning_minutes else "WATCHING"
        next_check = now + timedelta(minutes=self.interval_minutes)
        detail = observation.detail or f"Activity check in {activity} min"
        state = self.repository.save_observation(
            status=status,
            armed=True,
            activity_minutes=activity,
            activity_epoch=epoch,
            warning_sent=warned,
            observed_at=str(observation.observed_at or self._iso(now)),
            next_check_at=self._iso(next_check),
            detail=detail,
        )
        return RestModeCycleResult(state, warning_emitted=warning_emitted)

    def _observe_verified_cycle(self, expected: _IdentityAnchor, *, now: datetime) -> RestModeCycleResult:
        self._require_navigation_clear()
        before = self.navigation.observe()
        self._require_same_identity(before, expected)
        self.readiness.ensure_fleets()
        after = self.navigation.observe()
        self._require_same_identity(after, expected)
        observation = self.browser.read_rest_mode_observation(
            expected_server_host=expected.server_host,
            expected_account_fingerprint=expected.account_fingerprint,
            expected_planet_id=expected.planet_id,
            expected_coord=expected.planet_coord,
        )
        final = self.navigation.observe()
        self._require_same_identity(final, expected)
        return self._apply_observation(observation, now=now)

    def start(self, *, now: datetime | None = None) -> RestModeCycleResult:
        """Start after authority acquisition; caller releases authority if result is disarmed."""

        with self._cycle_lock:
            current = self.repository.read()
            if current.armed:
                raise RestModeError("Rest Mode is already armed")
            # A completed explicit Stop leaves the intent set so queued ticks remain
            # harmless. A later explicit Start is the only operation allowed to
            # begin a fresh Rest Mode epoch and therefore clears that intent here.
            self._stop_requested.clear()
            moment = self._utc_now(now)
            try:
                self._require_navigation_clear()
                initial_observation = self.navigation.observe()
                expected = self._anchor(initial_observation)
                self.repository.begin_start(
                    session_id=f"rest-mode:{uuid4().hex}",
                    server_host=expected.server_host,
                    account_fingerprint=expected.account_fingerprint,
                    planet_id=expected.planet_id,
                    planet_coord=expected.planet_coord,
                    started_at=self._iso(moment),
                )
                return self._observe_verified_cycle(expected, now=moment)
            except Exception as exc:
                return RestModeCycleResult(self._block_for_exception(exc))

    def tick(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> RestModeCycleResult:
        # This pre-lock check rejects ticks submitted after Stop intent is visible.
        # The second check inside the lock handles a tick that queued before Stop but
        # only acquired the cycle boundary after Stop was requested.
        if self._stop_requested.is_set():
            return RestModeCycleResult(self.repository.read())
        with self._cycle_lock:
            state = self.repository.read()
            if not state.armed or self._stop_requested.is_set():
                return RestModeCycleResult(state)
            moment = self._utc_now(now)
            if not force and state.due_at is not None and moment < state.due_at:
                return RestModeCycleResult(state)
            expected = _IdentityAnchor(
                server_host=state.server_host,
                account_fingerprint=state.account_fingerprint,
                planet_id=state.planet_id,
                planet_coord=state.planet_coord,
            )
            try:
                return self._observe_verified_cycle(expected, now=moment)
            except Exception as exc:
                return RestModeCycleResult(self._block_for_exception(exc))

    def block_busy(self, detail: str) -> RestModeState:
        self._stop_requested.set()
        with self._cycle_lock:
            return self.repository.block(status="BLOCKED_BUSY", detail=str(detail))

    def stop(self, *, detail: str = "Stopped by operator") -> RestModeState:
        # Stop intent is visible before waiting for the critical cycle. An already
        # active tick may safely drain, but queued/new ticks see the intent and must
        # perform zero new browser work. Persistence remains on the caller's owning
        # application thread in production; the lock is not a SQLite thread-safety
        # mechanism.
        self._stop_requested.set()
        with self._cycle_lock:
            return self.repository.stop(detail=detail)
