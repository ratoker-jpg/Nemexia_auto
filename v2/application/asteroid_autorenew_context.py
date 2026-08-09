from __future__ import annotations

from datetime import datetime
from typing import Mapping

from v2.application.asteroid_autorenew import AsteroidAutorenewService, AsteroidAutorenewTick
from v2.application.automation_authority import (
    ASTEROID_AUTORENEW_OWNER,
    AUTOFARM_OWNER,
    AutomationAuthority,
)
from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness
from v2.persistence.asteroid_autorenew import AsteroidAutorenewState


class AsteroidAutorenewApplicationContext(DebrisEnabledApplicationContextWithReadiness):
    """Typed AUTO-11 boundary plus one shared in-process automatic-mutation owner."""

    def __init__(
        self,
        *args,
        asteroid_autorenew: AsteroidAutorenewService | None = None,
        automation_authority: AutomationAuthority | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._asteroid_autorenew = asteroid_autorenew
        self._automation_authority = automation_authority or AutomationAuthority()

    def automation_cycle_owner(self) -> str | None:
        return self._automation_authority.owner()

    def ensure_automation_cycle_available(self, owner: str) -> None:
        self._automation_authority.ensure_available(owner)

    def acquire_automation_cycle(self, owner: str) -> str:
        return self._automation_authority.acquire(owner)

    def release_automation_cycle(self, owner: str) -> None:
        authority = getattr(self, "_automation_authority", None)
        if authority is not None and authority.owner() == str(owner):
            authority.release(owner)

    def asteroid_autorenew_state(self) -> AsteroidAutorenewState | None:
        service = self._asteroid_autorenew
        return None if service is None else service.state()

    def start_asteroid_autorenew(
        self,
        *,
        source: str,
        recycler_count: int = 5,
        max_flights: int = 15,
        safety_seconds: int = 10,
        buffer_minutes: int = 5,
        start_immediately: bool = True,
    ) -> AsteroidAutorenewTick:
        service = self._require_asteroid_autorenew()
        self.acquire_automation_cycle(ASTEROID_AUTORENEW_OWNER)
        try:
            result = service.start(
                source=source,
                recycler_count=recycler_count,
                max_flights=max_flights,
                safety_seconds=safety_seconds,
                buffer_minutes=buffer_minutes,
                start_immediately=start_immediately,
            )
        except Exception:
            self.release_automation_cycle(ASTEROID_AUTORENEW_OWNER)
            raise
        if not result.state.armed:
            self.release_automation_cycle(ASTEROID_AUTORENEW_OWNER)
        return result

    def stop_asteroid_autorenew(
        self,
        *,
        detail: str = "Stopped by operator",
    ) -> AsteroidAutorenewState:
        try:
            return self._require_asteroid_autorenew().stop(detail=detail)
        finally:
            self.release_automation_cycle(ASTEROID_AUTORENEW_OWNER)

    def tick_asteroid_autorenew(
        self,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> AsteroidAutorenewTick:
        result = self._require_asteroid_autorenew().tick(force=force, now=now)
        if not result.state.armed:
            self.release_automation_cycle(ASTEROID_AUTORENEW_OWNER)
        return result

    def run_farm_wave(self, *, ship_count: int, max_targets: int):
        """Manual/continuous farm mutations cannot run while asteroid auto owns authority."""

        self.ensure_automation_cycle_available(AUTOFARM_OWNER)
        return super().run_farm_wave(ship_count=ship_count, max_targets=max_targets)

    def _require_asteroid_autorenew(self) -> AsteroidAutorenewService:
        if self._asteroid_autorenew is None:
            raise RuntimeError("V2 asteroid autorenew service is unavailable")
        return self._asteroid_autorenew

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        parsed = super().set_v2_settings(values)
        service = self._asteroid_autorenew
        if service is not None and "actions_enabled" in parsed and not bool(parsed["actions_enabled"]):
            state = service.state()
            if state.armed:
                self.stop_asteroid_autorenew(detail="V2 actions were disabled")
        return parsed

    def close(self) -> None:
        service = self._asteroid_autorenew
        if service is not None:
            try:
                state = service.state()
                if state.armed:
                    # Use the service lifecycle so a running AUTO-10 discovery row
                    # is stopped before scheduler authority/active_scan_id is cleared.
                    service.stop(
                        detail="Application closed; explicit Start required on next launch"
                    )
            finally:
                self.release_automation_cycle(ASTEROID_AUTORENEW_OWNER)
                self.release_automation_cycle(AUTOFARM_OWNER)
                self._asteroid_autorenew = None
        super().close()
