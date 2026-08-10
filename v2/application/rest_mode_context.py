from __future__ import annotations

from datetime import datetime

from v2.application.asteroid_autorenew_context import AsteroidAutorenewApplicationContext
from v2.application.automation_authority import (
    REST_MODE_OWNER,
    AutomationAuthorityError,
)
from v2.application.rest_mode import RestModeCycleResult, RestModeService
from v2.persistence.rest_mode import RestModeState


class RestModeApplicationContext(AsteroidAutorenewApplicationContext):
    """Typed AUTO-12 boundary sharing one process-level browser authority."""

    def __init__(self, *args, rest_mode: RestModeService | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rest_mode = rest_mode

    def _require_rest_mode(self) -> RestModeService:
        if self._rest_mode is None:
            raise RuntimeError("V2 Rest Mode service is unavailable")
        return self._rest_mode

    def rest_mode_state(self) -> RestModeState | None:
        service = self._rest_mode
        return None if service is None else service.state()

    def start_rest_mode(self, *, now: datetime | None = None) -> RestModeCycleResult:
        service = self._require_rest_mode()
        try:
            self.acquire_automation_cycle(REST_MODE_OWNER)
        except AutomationAuthorityError as exc:
            state = service.block_busy(str(exc))
            return RestModeCycleResult(state)

        try:
            result = service.start(now=now)
        except Exception:
            self.release_automation_cycle(REST_MODE_OWNER)
            raise
        if not result.state.armed:
            self.release_automation_cycle(REST_MODE_OWNER)
        return result

    def tick_rest_mode(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> RestModeCycleResult:
        service = self._require_rest_mode()
        state = service.state()
        if not state.armed:
            return RestModeCycleResult(state)

        owner = self.automation_cycle_owner()
        if owner != REST_MODE_OWNER:
            blocked = service.block_busy(
                "Rest Mode lost its process-level browser authority; explicit Start required"
            )
            return RestModeCycleResult(blocked)

        try:
            result = service.tick(now=now, force=force)
        except Exception:
            # The service cycle lock has unwound before the exception reaches this
            # boundary, so it is safe to disarm/release without racing page work.
            try:
                service.stop(
                    detail="Unexpected Rest Mode tick failure; explicit Start required"
                )
            finally:
                self.release_automation_cycle(REST_MODE_OWNER)
            raise
        if not result.state.armed:
            # tick() returned only after its cycle lock was released, so releasing
            # the process-level owner here cannot race with more Rest Mode page work.
            self.release_automation_cycle(REST_MODE_OWNER)
        return result

    def stop_rest_mode(self, *, detail: str = "Stopped by operator") -> RestModeState:
        service = self._require_rest_mode()
        try:
            # RestModeService.stop() drains its serialized in-flight cycle first.
            return service.stop(detail=detail)
        finally:
            self.release_automation_cycle(REST_MODE_OWNER)

    def _require_rest_mode_browser_available(self) -> None:
        if self.automation_cycle_owner() == REST_MODE_OWNER:
            raise RuntimeError(
                "Browser context is owned by Rest Mode; stop Rest Mode before this operation"
            )

    # Normal application entrypoints below are the manual/automatic browser-driving
    # boundaries. RestModeService does not call them: it owns its dedicated typed
    # BrowserReadinessManager over the same NavigationCoordinator, so this gate cannot
    # deadlock the Rest Mode cycle itself.
    def ensure_fleets_ready(self, *, planet_coord: str | None = None):
        self._require_rest_mode_browser_available()
        return super().ensure_fleets_ready(planet_coord=planet_coord)

    def ensure_messages_ready(self, *, planet_coord: str | None = None):
        self._require_rest_mode_browser_available()
        return super().ensure_messages_ready(planet_coord=planet_coord)

    def ensure_galaxy_ready(self, *, planet_coord: str | None = None):
        self._require_rest_mode_browser_available()
        return super().ensure_galaxy_ready(planet_coord=planet_coord)

    def switch_owned_planet(self, *, planet_id: str, request_id: str):
        self._require_rest_mode_browser_available()
        return super().switch_owned_planet(planet_id=planet_id, request_id=request_id)

    def prepare_fleets_page(self, *, request_id: str):
        self._require_rest_mode_browser_available()
        return super().prepare_fleets_page(request_id=request_id)

    def prepare_system_messages(self, *, request_id: str):
        self._require_rest_mode_browser_available()
        return super().prepare_system_messages(request_id=request_id)

    def prepare_galaxy_page(self, *, request_id: str):
        self._require_rest_mode_browser_available()
        return super().prepare_galaxy_page(request_id=request_id)

    def prepare_spy(self, fleet_id: str):
        self._require_rest_mode_browser_available()
        return super().prepare_spy(fleet_id)

    def process_spy(self, fleet_id: str, *, request_id: str):
        self._require_rest_mode_browser_available()
        return super().process_spy(fleet_id, request_id=request_id)

    def run_automatic_recon(self, *, request_id: str):
        self._require_rest_mode_browser_available()
        return super().run_automatic_recon(request_id=request_id)

    def run_controlled_recon_refill(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().run_controlled_recon_refill(*args, **kwargs)

    def start_discovery_scan(self, *, scan_id: str, planet_coord: str | None = None):
        self._require_rest_mode_browser_available()
        return super().start_discovery_scan(scan_id=scan_id, planet_coord=planet_coord)

    def resume_discovery_scan(self, scan_id: str):
        self._require_rest_mode_browser_available()
        return super().resume_discovery_scan(scan_id)

    def step_discovery_scan(self, scan_id: str):
        self._require_rest_mode_browser_available()
        return super().step_discovery_scan(scan_id)

    def run_discovery_scan(self, scan_id: str, *, max_steps: int | None = None):
        self._require_rest_mode_browser_available()
        return super().run_discovery_scan(scan_id, max_steps=max_steps)

    def prepare_asteroid(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().prepare_asteroid(*args, **kwargs)

    def dispatch_asteroid(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().dispatch_asteroid(*args, **kwargs)

    def prepare_asteroid_candidates(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().prepare_asteroid_candidates(*args, **kwargs)

    def dispatch_asteroid_candidates(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().dispatch_asteroid_candidates(*args, **kwargs)

    def prepare_debris_candidates(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().prepare_debris_candidates(*args, **kwargs)

    def confirm_debris_candidates(self, *args, **kwargs):
        self._require_rest_mode_browser_available()
        return super().confirm_debris_candidates(*args, **kwargs)

    def close(self) -> None:
        service = getattr(self, "_rest_mode", None)
        if service is not None:
            try:
                state = service.state()
                if state.armed:
                    # Stop drains the cycle before we release authority or let
                    # superclass close tear down the shared navigation backend.
                    service.stop(
                        detail="Application closed; explicit Rest Mode Start required on next launch"
                    )
            finally:
                self.release_automation_cycle(REST_MODE_OWNER)
                self._rest_mode = None
        super().close()
