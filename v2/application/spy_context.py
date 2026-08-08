from __future__ import annotations

from typing import Mapping

from v2.application.context import V2ApplicationContext
from v2.application.spy_actions import SpyActionService, SpyRequestCommand, SpyRequestPreparation, SpyRequestResult
from v2.application.spy_journal import SpyActionRecord, SpyRequestCoordinator


class SpyEnabledApplicationContext(V2ApplicationContext):
    """V2 context extension exposing only manual journaled spy processing."""

    def __init__(self, *args, spy_actions: SpyActionService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._spy_actions = spy_actions

    def set_v2_settings(self, values: Mapping[str, object]) -> dict[str, object]:
        parsed = super().set_v2_settings(values)
        if "actions_enabled" in parsed:
            self._spy_actions.set_enabled(bool(parsed["actions_enabled"]))
        return parsed

    def spy_actions_enabled(self) -> bool:
        return bool(self._spy_actions.enabled)

    def prepare_spy(self, fleet_id: str) -> SpyRequestPreparation:
        return self._spy_actions.prepare(SpyRequestCommand(fleet_id=str(fleet_id)))

    def process_spy(self, fleet_id: str, *, request_id: str) -> SpyRequestResult:
        database = getattr(self, "_v2_database", None)
        if database is None:
            raise RuntimeError("V2 spy journal is unavailable")
        return SpyRequestCoordinator(self._spy_actions, database).request(
            SpyRequestCommand(fleet_id=str(fleet_id)),
            request_id=request_id,
        )

    def recent_spy_actions(self, *, limit: int = 200) -> list[SpyActionRecord]:
        database = getattr(self, "_v2_database", None)
        if database is None:
            return []
        return SpyRequestCoordinator(self._spy_actions, database).recent(limit=limit)

    def close(self) -> None:
        actions = getattr(self, "_spy_actions", None)
        if actions is not None:
            actions.close()
            self._spy_actions = None
        super().close()
