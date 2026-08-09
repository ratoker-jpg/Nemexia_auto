from __future__ import annotations

import threading


AUTOFARM_OWNER = "autofarm"
ASTEROID_AUTORENEW_OWNER = "asteroid_autorenew"


class AutomationAuthorityError(RuntimeError):
    pass


class AutomationAuthority:
    """Single-process owner token for mutually exclusive automatic mutation loops.

    The token is intentionally not persisted: both AutoFarm and asteroid autorenew
    start disarmed after process restart. Persistent action/navigation journals remain
    the authority for uncertain remote effects; this object only prevents two live
    schedulers from competing for the same browser/fleet capacity in one process.
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
                    f"Automatic mutation authority is owned by {self._owner}; "
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
