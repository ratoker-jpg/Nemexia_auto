from __future__ import annotations

import threading


AUTOFARM_OWNER = "autofarm"
ASTEROID_AUTORENEW_OWNER = "asteroid_autorenew"
REST_MODE_OWNER = "rest_mode"


class AutomationAuthorityError(RuntimeError):
    pass


class AutomationAuthority:
    """Single-process owner token for mutually exclusive automatic browser loops.

    The token is intentionally not persisted: AutoFarm, asteroid autorenew and
    Rest Mode start disarmed after process restart. Persistent action/navigation
    journals remain the authority for uncertain remote effects; this object only
    prevents live workflows from competing for the same coordinator-owned page.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._owner: str | None = None

    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def ensure_available(self, owner: str) -> None:
        requested = str(owner or "").strip()
        if not requested:
            raise AutomationAuthorityError("Automation owner is required")
        with self._lock:
            if self._owner not in {None, requested}:
                raise AutomationAuthorityError(
                    f"Automatic browser authority is owned by {self._owner}; "
                    f"{requested} cannot arm concurrently"
                )

    def acquire(self, owner: str) -> str:
        requested = str(owner or "").strip()
        self.ensure_available(requested)
        with self._lock:
            self._owner = requested
            return requested

    def release(self, owner: str) -> None:
        requested = str(owner or "").strip()
        if not requested:
            return
        with self._lock:
            if self._owner is None:
                return
            if self._owner != requested:
                raise AutomationAuthorityError(
                    f"Automation owner {requested} cannot release {self._owner} authority"
                )
            self._owner = None
