from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidActionsDisabled,
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchCommand,
    AsteroidDispatchResult,
    AsteroidPreparationRejected,
    normalize_coord,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.application.asteroid_repository import V2AsteroidRepository
from v2.application.browser_readiness import BrowserReadinessManager
from v2.application.discovery_scan import ControlledDiscoveryScan, DiscoverySystemEvidence
from v2.application.navigation import NavigationObservation
from v2.domain.asteroid_candidates import AsteroidCandidate, build_candidate_preview, observation_identity
from v2.domain.asteroids import predict_coordinate
from v2.persistence.asteroid_autorenew import AsteroidAutorenewRepository, AsteroidAutorenewState
from v2.persistence.asteroid_autorenew_guard import AsteroidAutorenewGuardRepository
from v2.persistence.database import V2Database


AUTORENEW_CAPTCHA_POLL_SECONDS = 20


class AutorenenwDiscoveryBrowser(Protocol):
    def read_discovery_system(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
        expected_galaxy: int,
        expected_solar: int,
    ) -> DiscoverySystemEvidence: ...


class AutorenenwNavigation(Protocol):
    def observe(self) -> NavigationObservation: ...
    def unresolved(self): ...
    def navigate_galaxy_system(self, *, request_id: str, galaxy: int, solar: int): ...


class AutorenenwCaptchaProbe(Protocol):
    def autorenew_captcha_present(self) -> bool: ...


class AsteroidAutorenewError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsteroidAutorenewTick:
    state: AsteroidAutorenewState
    remote_send_attempted: bool = False
    verified_send: bool = False
    detail: str = ""


class AsteroidAutorenewService:
    """AUTO-11 explicit, persistent, restart-disarmed asteroid repeat state machine.

    The service deliberately has no background thread. V2Database is thread-affine;
    callers drive `tick()` from the owning application execution context. One tick
    performs at most one discovery system step or one asteroid dispatch candidate,
    which leaves an explicit Stop boundary between future side effects.
    """

    def __init__(
        self,
        *,
        database: V2Database,
        navigation: AutorenenwNavigation,
        discovery: ControlledDiscoveryScan,
        discovery_browser: AutorenenwDiscoveryBrowser,
        asteroid_repository: V2AsteroidRepository,
        asteroid_actions: AsteroidActionService,
        captcha_probe: AutorenenwCaptchaProbe,
        now: Callable[[], datetime] | None = None,
        request_id: Callable[[], str] | None = None,
    ) -> None:
        self.database = database
        self.navigation = navigation
        self.readiness = BrowserReadinessManager(navigation)  # type: ignore[arg-type]
        self.discovery = discovery
        self.discovery_browser = discovery_browser
        self.asteroid_repository = asteroid_repository
        self.asteroid_actions = asteroid_actions
        self.captcha_probe = captcha_probe
        self.coordinator = AsteroidRequestCoordinator(asteroid_actions, database)
        self.repository = AsteroidAutorenewRepository(database)
        self.guard = AsteroidAutorenewGuardRepository(database)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._request_id = request_id or (lambda: uuid.uuid4().hex)
        self._lock = threading.RLock()
        self._cycle_candidates: tuple[AsteroidCandidate, ...] = ()
        self._candidate_index = 0
        self._cycle_results: dict[str, AsteroidDispatchResult] = {}
        self._scan_before_ids: frozenset[tuple[object, ...]] = frozenset()
        self._last_captcha_probe: datetime | None = None
        # Persisted armed=true is crash evidence only. A new process cannot inherit authority.
        self.repository.disarm_on_startup()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def state(self) -> AsteroidAutorenewState:
        return self.repository.read()

    def _navigation_unresolved(self):
        reader = getattr(self.navigation, "unresolved", None)
        return tuple(reader()) if callable(reader) else ()

    def _require_navigation_clear(self) -> None:
        unresolved = self._navigation_unresolved()
        if unresolved:
            first = unresolved[0]
            raise AsteroidAutorenewError(
                "Asteroid autorenew blocked by unresolved navigation "
                f"{getattr(first, 'request_id', 'unknown')} ({getattr(first, 'status', 'unresolved')}); "
                "zero new browser mutations attempted"
            )

    def _require_action_clear(self) -> None:
        unresolved = self.guard.unresolved_action()
        if unresolved is not None:
            raise AsteroidAutorenewError(
                f"Asteroid autorenew blocked by unresolved asteroid action "
                f"{unresolved.request_id} ({unresolved.status}); no new SendFleet attempt allowed"
            )

    @staticmethod
    def _source_from_observation(observation: NavigationObservation, source_coord: str):
        source = observation.identity.by_coord(source_coord)
        if source is None:
            raise AsteroidAutorenewError(
                f"Asteroid source {source_coord} is not in the proven owned PlanetIdentity set"
            )
        if not observation.identity.account.ownership_fingerprint:
            raise AsteroidAutorenewError("Account ownership fingerprint is not proven")
        return source

    def _require_expected_context(
        self,
        state: AsteroidAutorenewState,
        observation: NavigationObservation,
        *,
        page_kind: str | None = None,
        galaxy: int | None = None,
        solar: int | None = None,
    ) -> None:
        current = observation.identity.current_planet
        if observation.identity.account.ownership_fingerprint != state.account_fingerprint:
            raise AsteroidAutorenewError("Account identity changed during asteroid autorenew")
        if (
            current is None
            or current.planet_id != state.source_planet_id
            or current.coord != state.source_coord
        ):
            raise AsteroidAutorenewError("Selected source PlanetIdentity changed during asteroid autorenew")
        if page_kind == "galaxy":
            if not observation.page.galaxy_ready or observation.page.page_kind != "galaxy":
                raise AsteroidAutorenewError("Verified galaxy readiness was lost")
            if galaxy is not None and observation.page.galaxy != int(galaxy):
                raise AsteroidAutorenewError("Rendered galaxy changed during asteroid autorenew")
            if solar is not None and observation.page.solar != int(solar):
                raise AsteroidAutorenewError("Rendered solar system changed during asteroid autorenew")
        if page_kind == "fleets" and not observation.page.fleets_ready:
            raise AsteroidAutorenewError("Verified fleets readiness was lost")

    def start(
        self,
        *,
        source: str,
        recycler_count: int = 5,
        max_flights: int = 15,
        safety_seconds: int = 10,
        buffer_minutes: int = 5,
        start_immediately: bool = True,
    ) -> AsteroidAutorenewTick:
        """Explicitly arm one in-process autorenew session.

        All unresolved-effect checks and source proof happen before readiness can
        mutate the browser. `start_immediately` performs only the first state-machine
        tick; it does not hide a long-running loop inside Start.
        """

        with self._lock:
            if not self.asteroid_actions.enabled:
                raise AsteroidActionsDisabled("V2 asteroid actions are disabled")
            self._require_navigation_clear()
            self._require_action_clear()
            clean_source = normalize_coord(source)
            observed = self.navigation.observe()
            planet = self._source_from_observation(observed, clean_source)
            session_id = f"autorenew-{self._request_id()}"
            state = self.repository.arm(
                session_id=session_id,
                source_planet_id=planet.planet_id,
                source_coord=planet.coord,
                account_fingerprint=observed.identity.account.ownership_fingerprint,
                recycler_count=int(recycler_count),
                max_flights=int(max_flights),
                safety_seconds=int(safety_seconds),
                buffer_minutes=int(buffer_minutes),
            )
            self._cycle_candidates = ()
            self._candidate_index = 0
            self._cycle_results = {}
            self._scan_before_ids = frozenset()
            self._last_captcha_probe = None
        if start_immediately:
            return self.tick(force=True)
        return AsteroidAutorenewTick(state, detail="Asteroid autorenew explicitly armed")

    def stop(self, *, detail: str = "Stopped by operator") -> AsteroidAutorenewState:
        with self._lock:
            state = self.repository.read()
            if state.active_scan_id:
                scan = self.discovery.repository.read(state.active_scan_id)
                if scan is not None and scan.status == "running":
                    try:
                        self.discovery.stop(scan.scan_id, detail=detail)
                    except Exception:
                        pass
            self._cycle_candidates = ()
            self._candidate_index = 0
            self._cycle_results = {}
            self._scan_before_ids = frozenset()
            return self.repository.stop(status="stopped_manual", detail=detail)

    def _stop(self, status: str, detail: str) -> AsteroidAutorenewTick:
        state = self.repository.stop(status=status, detail=detail)
        return AsteroidAutorenewTick(state, detail=detail)

    def _block(self, exc: Exception) -> AsteroidAutorenewTick:
        text = str(exc) or exc.__class__.__name__
        return self._stop("blocked", text)

    def _start_cycle(self, state: AsteroidAutorenewState, now: datetime) -> AsteroidAutorenewTick:
        self._require_navigation_clear()
        self._require_action_clear()
        self.readiness.ensure_galaxy(planet_coord=state.source_coord)
        observed = self.navigation.observe()
        self._require_expected_context(state, observed, page_kind="galaxy")
        scan_id = f"autorenew-scan:{state.session_id}:{self._request_id()}"
        self._scan_before_ids = frozenset(self.discovery.asteroid_storage.identities())
        scan = self.discovery.start(scan_id=scan_id, planet_coord=state.source_coord)
        updated = self.repository.transition(
            status="running_discovery",
            armed=True,
            active_scan_id=scan.scan_id,
            cycle_started_at=now.isoformat(),
            verified_sent=0,
            detail="Refreshing current V2-owned asteroid evidence",
        )
        self._cycle_candidates = ()
        self._candidate_index = 0
        self._cycle_results = {}
        return AsteroidAutorenewTick(updated, detail=updated.detail)

    def _current_scan_candidates(self, now: datetime) -> tuple[AsteroidCandidate, ...]:
        observations = tuple(
            fact
            for fact in self.asteroid_repository.observations()
            if observation_identity(fact) not in self._scan_before_ids
        )
        if not observations:
            return ()
        return build_candidate_preview(
            persisted=(),
            incoming=observations,
            now=now,
        ).candidates

    def _discovery_tick(self, state: AsteroidAutorenewState, now: datetime) -> AsteroidAutorenewTick:
        if not state.active_scan_id:
            return self._stop("blocked", "Running discovery has no active scan identity")
        self._require_navigation_clear()
        result = self.discovery.step(state.active_scan_id)
        scan = result.scan
        if scan.status == "ambiguous":
            return self._stop("stopped_ambiguous", scan.detail or "Discovery navigation became ambiguous")
        if scan.status not in {"running", "completed"}:
            return self._stop("blocked", scan.detail or f"Discovery stopped with {scan.status}")
        if scan.status == "running":
            return AsteroidAutorenewTick(
                self.repository.transition(
                    status="running_discovery",
                    armed=True,
                    active_scan_id=scan.scan_id,
                    cycle_started_at=state.cycle_started_at,
                    verified_sent=0,
                    detail=f"Discovery progress {scan.cursor_index}/120",
                ),
                detail=f"Discovery progress {scan.cursor_index}/120",
            )

        candidates = self._current_scan_candidates(now)
        if not candidates:
            return self._stop(
                "stopped_no_asteroids",
                "Current completed discovery produced no new usable asteroid evidence",
            )
        self._cycle_candidates = candidates
        self._candidate_index = 0
        self._cycle_results = {}
        updated = self.repository.transition(
            status="running_dispatch",
            armed=True,
            active_scan_id=scan.scan_id,
            cycle_started_at=state.cycle_started_at,
            verified_sent=0,
            detail=f"Current discovery produced {len(candidates)} deterministic asteroid candidates",
        )
        return AsteroidAutorenewTick(updated, detail=updated.detail)

    def _fresh_candidate(
        self,
        state: AsteroidAutorenewState,
        candidate: AsteroidCandidate,
        now: datetime,
    ):
        try:
            current, _ = predict_coordinate(candidate.observation, now, safety_seconds=0)
        except ValueError:
            return None
        galaxy, solar, position = current
        self._require_navigation_clear()
        self.readiness.ensure_galaxy(planet_coord=state.source_coord)
        before = self.navigation.observe()
        self._require_expected_context(state, before, page_kind="galaxy")
        nav = self.navigation.navigate_galaxy_system(
            request_id=f"autorenew-system:{state.session_id}:{self._request_id()}",
            galaxy=galaxy,
            solar=solar,
        )
        if nav.status == "ambiguous":
            raise AsteroidDispatchAmbiguous(
                f"Galaxy navigation {galaxy}:{solar} became ambiguous; SendFleet forbidden"
            )
        if nav.status != "verified":
            raise AsteroidAutorenewError(
                f"Galaxy navigation {galaxy}:{solar} failed safely: {nav.detail}"
            )
        observed = self.navigation.observe()
        self._require_expected_context(
            state,
            observed,
            page_kind="galaxy",
            galaxy=galaxy,
            solar=solar,
        )
        evidence = self.discovery_browser.read_discovery_system(
            expected_planet_id=state.source_planet_id,
            expected_coord=state.source_coord,
            expected_account_fingerprint=state.account_fingerprint,
            expected_galaxy=galaxy,
            expected_solar=solar,
        )
        if not evidence.complete:
            raise AsteroidAutorenewError(
                f"Partial current asteroid evidence {galaxy}:{solar}: "
                f"visible={evidence.visible_asteroids}, readable={evidence.readable_square_info}"
            )
        matches = [
            fact for fact in evidence.asteroids
            if fact.galaxy == galaxy and fact.system == solar and fact.position == position
        ]
        if not matches:
            return None
        matches.sort(key=lambda fact: self._utc(fact.observed_at), reverse=True)
        fresh = matches[0]
        self.asteroid_repository.ingest((fresh,), now=now)
        return fresh

    def _request_identity(self, state: AsteroidAutorenewState, index: int) -> str:
        scan = state.active_scan_id or "no-scan"
        return f"asteroid-autorenew:{state.session_id}:{scan}:{int(index)}"

    def _remember_verified_record(self, request_id: str) -> bool:
        record = self.coordinator.record(request_id)
        if record is None or record.status != "verified" or not record.return_at:
            return False
        return_at = datetime.fromisoformat(record.return_at.replace("Z", "+00:00"))
        if return_at.tzinfo is None:
            return_at = return_at.replace(tzinfo=timezone.utc)
        self._cycle_results.setdefault(
            request_id,
            AsteroidDispatchResult(
                source=record.source,
                observation_coord=record.observation_coord,
                target=record.target,
                recycler_count=record.recycler_count,
                sent_at=(
                    datetime.fromisoformat(record.sent_at.replace("Z", "+00:00"))
                    if record.sent_at else self._now()
                ),
                arrival_at=(
                    datetime.fromisoformat(record.arrival_at.replace("Z", "+00:00"))
                    if record.arrival_at else return_at
                ),
                return_at=return_at,
                fleet_id=record.fleet_id,
                verified=True,
                server_info=record.detail,
            ),
        )
        return True

    def _schedule_after_verified(self, state: AsteroidAutorenewState) -> AsteroidAutorenewTick:
        results = tuple(self._cycle_results.values())
        if not results:
            return self._stop("stopped_no_asteroids", "Cycle produced no verified asteroid flights")
        latest = max(self._utc(item.return_at) for item in results)
        next_cycle = latest + timedelta(minutes=max(0, int(state.buffer_minutes)))
        updated = self.repository.transition(
            status="waiting_return",
            armed=True,
            next_cycle_at=next_cycle.isoformat(),
            active_scan_id=None,
            cycle_started_at=state.cycle_started_at,
            last_return_at=latest.isoformat(),
            verified_sent=len(results),
            detail=(
                f"Verified {len(results)} asteroid flights; next cycle after latest return "
                f"+ {state.buffer_minutes} min buffer"
            ),
        )
        self._cycle_candidates = ()
        self._candidate_index = 0
        self._scan_before_ids = frozenset()
        return AsteroidAutorenewTick(updated, detail=updated.detail)

    @staticmethod
    def _capacity_error(exc: Exception) -> bool:
        text = str(exc).casefold()
        return any(token in text for token in ("fleet slot", "свободн", "переработ", "recycler"))

    def _dispatch_tick(self, state: AsteroidAutorenewState, now: datetime) -> AsteroidAutorenewTick:
        if not self._cycle_candidates:
            return self._stop(
                "blocked",
                "In-process candidate snapshot is missing; restart remains disarmed and cannot resume it",
            )
        if len(self._cycle_results) >= state.max_flights:
            return self._schedule_after_verified(state)
        if self._candidate_index >= len(self._cycle_candidates):
            if self._cycle_results:
                return self._stop(
                    "stopped_insufficient",
                    f"Verified only {len(self._cycle_results)} flights before current candidates were exhausted",
                )
            return self._stop("stopped_no_asteroids", "No current asteroid candidate remained dispatchable")

        index = self._candidate_index
        candidate = self._cycle_candidates[index]
        request_id = self._request_identity(state, index)
        existing = self.coordinator.record(request_id)
        if existing is not None:
            if existing.status in {"pending", "ambiguous"}:
                return self._stop(
                    "stopped_ambiguous",
                    f"Existing autorenew request {request_id} is {existing.status}; automatic retry forbidden",
                )
            self._candidate_index += 1
            if existing.status == "verified":
                self._remember_verified_record(request_id)
                updated = self.repository.transition(
                    status="running_dispatch",
                    armed=True,
                    active_scan_id=state.active_scan_id,
                    cycle_started_at=state.cycle_started_at,
                    verified_sent=len(self._cycle_results),
                    detail="Recovered already-verified immutable autorenew request without another SendFleet",
                )
                return AsteroidAutorenewTick(updated, verified_send=True, detail=updated.detail)
            return AsteroidAutorenewTick(
                self.repository.transition(
                    status="running_dispatch",
                    armed=True,
                    active_scan_id=state.active_scan_id,
                    cycle_started_at=state.cycle_started_at,
                    verified_sent=len(self._cycle_results),
                    detail=f"Skipped prior failed-safe request {request_id}; no automatic retry for same candidate",
                ),
                detail=f"Skipped failed-safe request {request_id}",
            )

        fresh = self._fresh_candidate(state, candidate, now)
        if fresh is None:
            self._candidate_index += 1
            updated = self.repository.transition(
                status="running_dispatch",
                armed=True,
                active_scan_id=state.active_scan_id,
                cycle_started_at=state.cycle_started_at,
                verified_sent=len(self._cycle_results),
                detail=f"Candidate {index + 1}/{len(self._cycle_candidates)} is no longer visible; skipped safely",
            )
            return AsteroidAutorenewTick(updated, detail=updated.detail)

        self._require_navigation_clear()
        self._require_action_clear()
        self.readiness.ensure_fleets(planet_coord=state.source_coord)
        fleets = self.navigation.observe()
        self._require_expected_context(state, fleets, page_kind="fleets")
        command = AsteroidDispatchCommand(
            source=state.source_coord,
            observation=fresh,
            recycler_count=state.recycler_count,
            safety_seconds=state.safety_seconds,
        )
        try:
            result = self.coordinator.dispatch(command, request_id=request_id)
        except AsteroidCaptchaBlocked as exc:
            return self._stop("stopped_captcha", str(exc))
        except AsteroidDispatchAmbiguous as exc:
            return self._stop("stopped_ambiguous", str(exc))
        except AsteroidRequestBlocked as exc:
            unresolved = self.guard.unresolved_action()
            if unresolved is not None:
                return self._stop("stopped_ambiguous", str(exc))
            self._candidate_index += 1
            return AsteroidAutorenewTick(
                self.repository.transition(
                    status="running_dispatch",
                    armed=True,
                    active_scan_id=state.active_scan_id,
                    cycle_started_at=state.cycle_started_at,
                    verified_sent=len(self._cycle_results),
                    detail=str(exc),
                ),
                detail=str(exc),
            )
        except AsteroidPreparationRejected as exc:
            if self._capacity_error(exc):
                if self._cycle_results:
                    return self._schedule_after_verified(state)
                return self._stop("stopped_capacity", str(exc))
            self._candidate_index += 1
            return AsteroidAutorenewTick(
                self.repository.transition(
                    status="running_dispatch",
                    armed=True,
                    active_scan_id=state.active_scan_id,
                    cycle_started_at=state.cycle_started_at,
                    verified_sent=len(self._cycle_results),
                    detail=f"Candidate rejected safely: {exc}",
                ),
                detail=str(exc),
            )
        except Exception as exc:
            record = self.coordinator.record(request_id)
            if record is not None and record.status in {"pending", "ambiguous"}:
                return self._stop("stopped_ambiguous", str(exc))
            return self._block(exc)

        # Persisted asteroid action is already verified at this point. If context
        # verification fails now, stop future sends but never reinterpret/retry it.
        self._cycle_results[request_id] = result
        self._candidate_index += 1
        try:
            after = self.navigation.observe()
            self._require_expected_context(state, after, page_kind="fleets")
        except Exception as exc:
            return self._stop(
                "blocked",
                f"Verified asteroid flight {result.fleet_id}; future sends stopped because context changed: {exc}",
            )
        updated = self.repository.transition(
            status="running_dispatch",
            armed=True,
            active_scan_id=state.active_scan_id,
            cycle_started_at=state.cycle_started_at,
            verified_sent=len(self._cycle_results),
            detail=f"Verified asteroid flight {len(self._cycle_results)}/{state.max_flights}: {result.fleet_id}",
        )
        return AsteroidAutorenewTick(
            updated,
            remote_send_attempted=True,
            verified_send=True,
            detail=updated.detail,
        )

    def _waiting_tick(self, state: AsteroidAutorenewState, now: datetime, *, force: bool) -> AsteroidAutorenewTick:
        due = state.due_at
        if not force and due is not None and due > now:
            if (
                self._last_captcha_probe is None
                or (now - self._last_captcha_probe).total_seconds() >= AUTORENEW_CAPTCHA_POLL_SECONDS
            ):
                self._last_captcha_probe = now
                try:
                    if self.captcha_probe.autorenew_captcha_present():
                        return self._stop(
                            "stopped_captcha",
                            "CAPTCHA detected while waiting; explicit Start required after manual handling",
                        )
                except Exception as exc:
                    return self._stop(
                        "blocked",
                        f"Browser/CAPTCHA readiness probe failed while waiting: {exc}",
                    )
            return AsteroidAutorenewTick(state, detail=state.detail)
        updated = self.repository.transition(
            status="armed_due",
            armed=True,
            next_cycle_at=None,
            active_scan_id=None,
            verified_sent=0,
            detail="Latest verified asteroid fleet returned and buffer elapsed",
        )
        return AsteroidAutorenewTick(updated, detail=updated.detail)

    def tick(self, *, force: bool = False, now: datetime | None = None) -> AsteroidAutorenewTick:
        """Advance at most one scheduler step; never spin hidden remote effects."""

        with self._lock:
            current_now = self._utc(now or self._now())
            state = self.repository.read()
            if not state.armed:
                return AsteroidAutorenewTick(state, detail=state.detail)
            try:
                if state.status == "waiting_return":
                    return self._waiting_tick(state, current_now, force=force)
                if state.status == "armed_due":
                    return self._start_cycle(state, current_now)
                if state.status == "running_discovery":
                    return self._discovery_tick(state, current_now)
                if state.status == "running_dispatch":
                    return self._dispatch_tick(state, current_now)
                return self._stop("blocked", f"Unexpected armed autorenew state: {state.status}")
            except AsteroidCaptchaBlocked as exc:
                return self._stop("stopped_captcha", str(exc))
            except AsteroidDispatchAmbiguous as exc:
                return self._stop("stopped_ambiguous", str(exc))
            except AsteroidAutorenewError as exc:
                if self._navigation_unresolved() or self.guard.unresolved_action() is not None:
                    return self._stop("stopped_ambiguous", str(exc))
                return self._block(exc)
            except Exception as exc:
                if self._navigation_unresolved() or self.guard.unresolved_action() is not None:
                    return self._stop("stopped_ambiguous", str(exc))
                return self._block(exc)
