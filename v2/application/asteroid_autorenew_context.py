from __future__ import annotations

from datetime import datetime
from typing import Mapping

from v2.application.asteroid_autorenew import AsteroidAutorenewService, AsteroidAutorenewTick
from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness
from v2.persistence.asteroid_autorenew import AsteroidAutorenewState


class AsteroidAutorenewApplicationContext(DebrisEnabledApplicationContextWithReadiness):
    """Typed AUTO-11 boundary; Qt never touches browser selectors or CDP."""

    def __init__(
        self,
        *args,
        asteroid_autorenew: AsteroidAutorenewService | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._asteroid_autorenew = asteroid_autorenew

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
        return service.start(
            source=source,
            recycler_count=recycler_count,
            max_flights=max_flights,
            safety_seconds=safety_seconds,
            buffer_minutes=buffer_minutes,
            start_immediately=start_immediately,
        )

    def stop_asteroid_autorenew(
        self,
        *,
        detail: str = "Stopped by operator",
    ) -> AsteroidAutorenewState:
        return self._require_asteroid_autorenew().stop(detail=detail)

    def tick_asteroid_autorenew(
        self,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> AsteroidAutorenewTick:
        return self._require_asteroid_autorenew().tick(force=force, now=now)

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
                service.stop(detail="V2 actions were disabled")
        return parsed

    def close(self) -> None:
        service = self._asteroid_autorenew
        if service is not None:
            try:
                state = service.state()
                if state.armed:
                    service.repository.stop(
                        status="disarmed",
                        detail="Application closed; explicit Start required on next launch",
                    )
            finally:
                self._asteroid_autorenew = None
        super().close()
