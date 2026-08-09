from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from v2.application.debris_repository import V2DebrisRepository
from v2.application.navigation import NavigationObservation
from v2.domain.asteroids import AsteroidObservationFact
from v2.domain.debris import DebrisObservationFact
from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.discovery_scan import (
    DISCOVERY_SYSTEM_COUNT,
    DiscoveryScanRecord,
    DiscoveryScanRepository,
)


DISCOVERY_SEQUENCE: tuple[tuple[int, int], ...] = tuple(
    (galaxy, solar)
    for galaxy in range(1, 4)
    for solar in range(40, 0, -1)
)
assert len(DISCOVERY_SEQUENCE) == DISCOVERY_SYSTEM_COUNT


@dataclass(frozen=True)
class DiscoverySystemEvidence:
    galaxy: int
    solar: int
    observed_server_at: datetime
    visible_asteroids: int
    readable_square_info: int
    asteroids: tuple[AsteroidObservationFact, ...]
    debris: tuple[DebrisObservationFact, ...]

    @property
    def complete(self) -> bool:
        return self.visible_asteroids == self.readable_square_info


@dataclass(frozen=True)
class DiscoveryStepResult:
    scan: DiscoveryScanRecord
    processed: bool
    galaxy: int | None = None
    solar: int | None = None
    asteroid_count: int = 0
    debris_count: int = 0


class DiscoveryBrowser(Protocol):
    def read_discovery_system(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
        expected_galaxy: int,
        expected_solar: int,
    ) -> DiscoverySystemEvidence: ...


class DiscoveryNavigation(Protocol):
    def observe(self) -> NavigationObservation: ...
    def prepare_galaxy(self, *, request_id: str): ...
    def navigate_galaxy_system(self, *, request_id: str, galaxy: int, solar: int): ...
    def unresolved(self): ...


class ControlledDiscoveryScan:
    """Persistent AUTO-10 stepper over the legacy-equivalent 3×40 sequence."""

    def __init__(
        self,
        *,
        browser: DiscoveryBrowser,
        navigation: DiscoveryNavigation,
        repository: DiscoveryScanRepository,
        asteroid_storage: AsteroidObservationRepository,
        debris_repository: V2DebrisRepository,
    ) -> None:
        self.browser = browser
        self.navigation = navigation
        self.repository = repository
        self.asteroid_storage = asteroid_storage
        self.debris_repository = debris_repository

    @staticmethod
    def _current(observation: NavigationObservation):
        current = observation.identity.current_planet
        if current is None:
            raise RuntimeError("Discovery requires a proven selected PlanetIdentity")
        return current

    @staticmethod
    def _same_scan_context(scan: DiscoveryScanRecord, observation: NavigationObservation) -> bool:
        current = observation.identity.current_planet
        return bool(
            current is not None
            and observation.identity.account.ownership_fingerprint == scan.account_fingerprint
            and current.planet_id == scan.planet_id
            and current.coord == scan.planet_coord
            and observation.page.page_kind == "galaxy"
            and observation.page.galaxy_ready
        )

    def _unresolved_navigation(self):
        reader = getattr(self.navigation, "unresolved", None)
        return tuple(reader()) if callable(reader) else ()

    def start(self, *, scan_id: str, planet_coord: str | None = None) -> DiscoveryScanRecord:
        if self._unresolved_navigation():
            raise RuntimeError("Discovery cannot start while navigation has unresolved effects")
        prepare_id = f"discovery-prepare:{scan_id}:{uuid.uuid4().hex}"
        prepare = self.navigation.prepare_galaxy(request_id=prepare_id)
        if getattr(prepare, "status", None) != "verified":
            raise RuntimeError(f"Galaxy preparation is not verified: {getattr(prepare, 'detail', '')}")
        before = self.navigation.observe()
        current = self._current(before)
        if planet_coord is not None and str(planet_coord) != current.coord:
            raise RuntimeError(
                "Discovery start must use the currently verified selected planet; "
                "prepare/switch the intended own planet before starting"
            )
        return self.repository.begin(
            scan_id=str(scan_id),
            account_fingerprint=before.identity.account.ownership_fingerprint,
            planet_id=current.planet_id,
            planet_coord=current.coord,
        )

    def resume(self, scan_id: str) -> DiscoveryScanRecord:
        if self._unresolved_navigation():
            raise RuntimeError(
                "Discovery resume blocked by unresolved navigation evidence; reconcile it first"
            )
        return self.repository.resume(str(scan_id))

    def stop(self, scan_id: str, *, detail: str = "Stopped by operator") -> DiscoveryScanRecord:
        return self.repository.finish_safe(str(scan_id), status="stopped", detail=detail)

    def step(self, scan_id: str) -> DiscoveryStepResult:
        scan = self.repository.read(str(scan_id))
        if scan is None:
            raise RuntimeError(f"Discovery scan not found: {scan_id}")
        if scan.status != "running":
            return DiscoveryStepResult(scan, processed=False)
        if scan.cursor_index >= DISCOVERY_SYSTEM_COUNT:
            completed = self.repository.complete(scan.scan_id)
            return DiscoveryStepResult(completed, processed=False)
        unresolved = self._unresolved_navigation()
        if unresolved:
            ambiguous = self.repository.finish_safe(
                scan.scan_id,
                status="ambiguous",
                detail=(
                    "Navigation has unresolved effect; discovery cursor was not advanced and "
                    "automatic retry is blocked"
                ),
            )
            return DiscoveryStepResult(ambiguous, processed=False)

        before = self.navigation.observe()
        if not self._same_scan_context(scan, before):
            failed = self.repository.finish_safe(
                scan.scan_id,
                status="failed_safe",
                detail="Account/planet/galaxy context changed before discovery step",
            )
            return DiscoveryStepResult(failed, processed=False)

        index = scan.cursor_index
        galaxy, solar = DISCOVERY_SEQUENCE[index]
        navigation_id = f"discovery-system:{scan.scan_id}:{index}:{uuid.uuid4().hex}"
        nav = self.navigation.navigate_galaxy_system(
            request_id=navigation_id,
            galaxy=galaxy,
            solar=solar,
        )
        if nav.status == "ambiguous":
            ambiguous = self.repository.finish_safe(
                scan.scan_id,
                status="ambiguous",
                detail=(
                    f"Galaxy navigation {galaxy}:{solar} is ambiguous; cursor remains {index}; "
                    "automatic retry forbidden"
                ),
            )
            return DiscoveryStepResult(ambiguous, processed=False, galaxy=galaxy, solar=solar)
        if nav.status != "verified":
            failed = self.repository.finish_safe(
                scan.scan_id,
                status="failed_safe",
                detail=f"Galaxy navigation {galaxy}:{solar} failed safely: {nav.detail}",
            )
            return DiscoveryStepResult(failed, processed=False, galaxy=galaxy, solar=solar)

        after = self.navigation.observe()
        if not self._same_scan_context(scan, after):
            ambiguous = self.repository.finish_safe(
                scan.scan_id,
                status="ambiguous",
                detail="Context changed after verified system navigation; cursor not advanced",
            )
            return DiscoveryStepResult(ambiguous, processed=False, galaxy=galaxy, solar=solar)
        if after.page.galaxy != galaxy or after.page.solar != solar:
            ambiguous = self.repository.finish_safe(
                scan.scan_id,
                status="ambiguous",
                detail="Rendered galaxy/system no longer matches the verified navigation result",
            )
            return DiscoveryStepResult(ambiguous, processed=False, galaxy=galaxy, solar=solar)

        try:
            evidence = self.browser.read_discovery_system(
                expected_planet_id=scan.planet_id,
                expected_coord=scan.planet_coord,
                expected_account_fingerprint=scan.account_fingerprint,
                expected_galaxy=galaxy,
                expected_solar=solar,
            )
        except Exception as exc:
            failed = self.repository.finish_safe(
                scan.scan_id,
                status="failed_safe",
                detail=f"Current-system evidence read failed: {exc}",
            )
            return DiscoveryStepResult(failed, processed=False, galaxy=galaxy, solar=solar)

        if not evidence.complete:
            failed = self.repository.finish_safe(
                scan.scan_id,
                status="failed_safe",
                detail=(
                    f"Partial system evidence {galaxy}:{solar}: visible={evidence.visible_asteroids}, "
                    f"readable={evidence.readable_square_info}"
                ),
            )
            return DiscoveryStepResult(failed, processed=False, galaxy=galaxy, solar=solar)
        if evidence.galaxy != galaxy or evidence.solar != solar:
            failed = self.repository.finish_safe(
                scan.scan_id,
                status="failed_safe",
                detail="Read evidence does not match requested galaxy/system",
            )
            return DiscoveryStepResult(failed, processed=False, galaxy=galaxy, solar=solar)

        self.asteroid_storage.upsert_many(
            [
                {
                    "galaxy": item.galaxy,
                    "system": item.system,
                    "position": item.position,
                    "last_move_at": item.last_move_at.isoformat(),
                    "next_move_at": item.next_move_at.isoformat(),
                    "period_seconds": item.period_seconds,
                    "observed_at": item.observed_at.isoformat(),
                    "source": item.source,
                }
                for item in evidence.asteroids
            ]
        )
        self.debris_repository.ingest(
            evidence.debris,
            now=evidence.observed_server_at.replace(tzinfo=timezone.utc),
        )
        advanced = self.repository.record_system(
            scan_id=scan.scan_id,
            sequence_index=index,
            galaxy=galaxy,
            solar=solar,
            asteroid_count=len(evidence.asteroids),
            debris_count=len(evidence.debris),
            observed_at=evidence.observed_server_at.isoformat(),
        )
        if advanced.cursor_index == DISCOVERY_SYSTEM_COUNT:
            advanced = self.repository.complete(scan.scan_id)
        return DiscoveryStepResult(
            advanced,
            processed=True,
            galaxy=galaxy,
            solar=solar,
            asteroid_count=len(evidence.asteroids),
            debris_count=len(evidence.debris),
        )

    def run(self, scan_id: str, *, max_steps: int | None = None) -> DiscoveryScanRecord:
        steps = 0
        while True:
            scan = self.repository.read(str(scan_id))
            if scan is None:
                raise RuntimeError(f"Discovery scan not found: {scan_id}")
            if scan.status != "running" or scan.done:
                return scan
            if max_steps is not None and steps >= max(0, int(max_steps)):
                return scan
            result = self.step(scan.scan_id)
            steps += 1
            if not result.processed or result.scan.status != "running":
                return result.scan

    def last_completed(self) -> DiscoveryScanRecord | None:
        return self.repository.last_completed()
