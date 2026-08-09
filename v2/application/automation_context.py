from __future__ import annotations

from datetime import datetime

from v2.application.browser_readiness import (
    BrowserReadinessError,
    BrowserReadinessManager,
    BrowserReadinessSnapshot,
)
from v2.application.debris_context import DebrisEnabledApplicationContext
from v2.application.flight_source import FlightSourceStatus
from v2.application.report_source import ReconReadSnapshot
from v2.domain.recon import LEGACY_SPY_REPORT_LOOKBACK_HOURS, ReportReadState


class DebrisEnabledApplicationContextWithReadiness(DebrisEnabledApplicationContext):
    """V2 context that prepares recoverable browser state through NavigationCoordinator."""

    def __init__(self, *args, navigation_coordinator=None, **kwargs) -> None:
        super().__init__(
            *args,
            navigation_coordinator=navigation_coordinator,
            **kwargs,
        )
        self._browser_readiness = (
            BrowserReadinessManager(navigation_coordinator)
            if navigation_coordinator is not None
            else None
        )

    def browser_readiness(self) -> BrowserReadinessSnapshot | None:
        if self._browser_readiness is None:
            return None
        return self._browser_readiness.snapshot()

    def ensure_fleets_ready(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if self._browser_readiness is None:
            raise BrowserReadinessError("Browser readiness manager is unavailable")
        return self._browser_readiness.ensure_fleets(planet_coord=planet_coord)

    def ensure_messages_ready(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if self._browser_readiness is None:
            raise BrowserReadinessError("Browser readiness manager is unavailable")
        return self._browser_readiness.ensure_messages(planet_coord=planet_coord)

    def ensure_galaxy_ready(self, *, planet_coord: str | None = None) -> BrowserReadinessSnapshot:
        if self._browser_readiness is None:
            raise BrowserReadinessError("Browser readiness manager is unavailable")
        return self._browser_readiness.ensure_galaxy(planet_coord=planet_coord)

    def refresh_live_source(self) -> FlightSourceStatus:
        """Normal live-flight refresh now prepares fleets.php automatically when safe."""

        try:
            self.ensure_fleets_ready()
        except BrowserReadinessError as exc:
            status = FlightSourceStatus(False, f"Browser readiness: {exc}")
            self._last_flight_status = status
            self._live_snapshot_ready = True
            self._last_active_flights = ()
            self._last_owned_planets = ()
            self._last_capacity = None
            return status
        return super().refresh_live_source()

    def live_recon(
        self,
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconReadSnapshot:
        """Normal recon read prepares options/System messages instead of asking the user."""

        try:
            self.ensure_messages_ready()
        except BrowserReadinessError as exc:
            return ReconReadSnapshot(
                ReportReadState.LIVE_UNAVAILABLE,
                (),
                (),
                (),
                f"Browser readiness: {exc}",
            )
        return super().live_recon(now=now, lookback_hours=lookback_hours)

    def prepare_raid(self, target: str, player: str, ship_count: int):
        home = str(self.v2_setting("farm_home", "") or "").strip()
        self.ensure_fleets_ready(planet_coord=home or None)
        return super().prepare_raid(target, player, ship_count)

    def dispatch_plan_raid(
        self,
        *,
        queue_id: int,
        target: str,
        player: str,
        ship_count: int,
        request_id: str,
    ):
        home = str(self.v2_setting("farm_home", "") or "").strip()
        self.ensure_fleets_ready(planet_coord=home or None)
        return super().dispatch_plan_raid(
            queue_id=queue_id,
            target=target,
            player=player,
            ship_count=ship_count,
            request_id=request_id,
        )

    def live_asteroids(self):
        """Observation reads prepare galaxy.php; system selection remains AUTO-09."""

        self.ensure_galaxy_ready()
        return super().live_asteroids()

    def live_debris(self):
        self.ensure_galaxy_ready()
        return super().live_debris()
