from __future__ import annotations

from datetime import datetime
from typing import Mapping

from v2.application.automatic_recon import AutomaticReconService
from v2.application.browser_readiness import (
    BrowserReadinessError,
    BrowserReadinessManager,
    BrowserReadinessSnapshot,
)
from v2.application.debris_context import DebrisEnabledApplicationContext
from v2.application.flight_source import FlightSourceStatus
from v2.application.report_source import ReconReadSnapshot
from v2.application.spy_actions import SpyRequestResult
from v2.domain.recon import LEGACY_SPY_REPORT_LOOKBACK_HOURS, ReportReadState
from v2.persistence.automatic_recon_journal import AutomaticReconJournalRecord


class DebrisEnabledApplicationContextWithReadiness(DebrisEnabledApplicationContext):
    """V2 context that prepares recoverable browser state through NavigationCoordinator."""

    def __init__(
        self,
        *args,
        navigation_coordinator=None,
        automatic_recon: AutomaticReconService | None = None,
        **kwargs,
    ) -> None:
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
        self._automatic_recon = automatic_recon

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        parsed = super().set_v2_settings(values)
        if self._automatic_recon is not None and "actions_enabled" in parsed:
            self._automatic_recon.set_enabled(bool(parsed["actions_enabled"]))
        return parsed

    def automatic_recon_enabled(self) -> bool:
        return bool(self._automatic_recon is not None and self._automatic_recon.enabled)

    def run_automatic_recon(self, *, request_id: str) -> SpyRequestResult:
        if self._automatic_recon is None:
            raise RuntimeError("V2 automatic recon service is unavailable")
        return self._automatic_recon.run(request_id=str(request_id))

    def recent_automatic_recon_actions(
        self,
        *,
        limit: int = 200,
    ) -> tuple[AutomaticReconJournalRecord, ...]:
        if self._automatic_recon is None:
            return ()
        return self._automatic_recon.journal.recent(limit=limit)

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
            state = (
                ReportReadState.CAPTCHA
                if "captcha" in str(exc).casefold()
                else ReportReadState.LIVE_UNAVAILABLE
            )
            return ReconReadSnapshot(
                state,
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

    def _validate_plan_raid_before_readiness(self, *, queue_id: int, target: str) -> None:
        """Reject commands guaranteed to fail locally before changing browser context."""

        if self._raid_actions is None or self._v2_database is None or self._v2_queue is None:
            raise RuntimeError("V2 raid dispatch services are unavailable")
        item = next((row for row in self.plan() if row.id == int(queue_id)), None)
        if item is None:
            raise RuntimeError(f"Queue row not found: {queue_id}")
        if item.coord != str(target):
            raise RuntimeError("Selected queue row changed; refresh Plan before sending")
        if item.state != "queued":
            raise RuntimeError(f"Queue row is not queued: {item.state}")
        if not item.enabled:
            raise RuntimeError(f"Target is disabled: {item.coord}")
        if item.blacklisted:
            raise RuntimeError(f"Target is blacklisted: {item.coord}")

    def dispatch_plan_raid(
        self,
        *,
        queue_id: int,
        target: str,
        player: str,
        ship_count: int,
        request_id: str,
    ):
        # Preserve the superclass validation again after readiness too, but do the
        # same local gate first so a stale/blocked command cannot switch planet or page.
        self._validate_plan_raid_before_readiness(queue_id=queue_id, target=target)
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

    def close(self) -> None:
        self._automatic_recon = None
        super().close()
