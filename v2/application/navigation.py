from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping, Protocol

from v2.application.browser_identity import BrowserIdentitySnapshot
from v2.persistence.navigation_journal import (
    NavigationJournalRecord,
    NavigationJournalRepository,
)


@dataclass(frozen=True)
class NavigationObservation:
    """Exact in-process page ownership plus read-only account/planet identity."""

    page_token: str
    identity: BrowserIdentitySnapshot

    def context_dict(self) -> dict[str, object]:
        current = self.identity.current_planet
        return {
            "page_token": self.page_token,
            "endpoint": self.identity.session.endpoint,
            "page_url": self.identity.session.page_url,
            "server_host": self.identity.session.server_host,
            "account_fingerprint": self.identity.account.ownership_fingerprint,
            "planet_id": current.planet_id if current is not None else "",
            "planet_coord": current.coord if current is not None else "",
        }


class NavigationBackend(Protocol):
    """Infrastructure boundary owned exclusively by NavigationCoordinator."""

    def observe(self) -> NavigationObservation: ...

    def close(self) -> None: ...


class NavigationCoordinator:
    """Serialize browser context ownership and persist mutation intent/results.

    AUTO-03 deliberately exposes observation/journal primitives only. Concrete
    browser mutations are added one operation at a time in AUTO-04/AUTO-05/AUTO-09.
    Feature services and Qt must never call Playwright/CDP selectors directly.
    """

    def __init__(
        self,
        backend: NavigationBackend,
        journal: NavigationJournalRepository,
    ) -> None:
        self._backend = backend
        self._journal = journal
        self._mutex = threading.RLock()
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("NavigationCoordinator is closed")

    def observe(self) -> NavigationObservation:
        with self._mutex:
            self._require_open()
            return self._backend.observe()

    def begin_request(
        self,
        *,
        request_id: str,
        action_kind: str,
        intent: Mapping[str, object],
    ) -> NavigationJournalRecord:
        """Persist immutable intent before a future remote context mutation.

        A request ID can be inserted only once. Callers must not catch duplicate
        request errors and retry with the same remote action.
        """

        with self._mutex:
            self._require_open()
            before = self._backend.observe().context_dict()
            return self._journal.begin(
                request_id=request_id,
                action_kind=action_kind,
                before=before,
                intent=dict(intent),
            )

    def finish_request(
        self,
        request_id: str,
        *,
        status: str,
        detail: str = "",
        observe_after: bool = True,
    ) -> NavigationJournalRecord:
        with self._mutex:
            self._require_open()
            after = self._backend.observe().context_dict() if observe_after else None
            return self._journal.finish(
                request_id,
                status=status,
                after=after,
                detail=detail,
            )

    def record(self, request_id: str) -> NavigationJournalRecord | None:
        with self._mutex:
            self._require_open()
            return self._journal.read(request_id)

    def recent(self, *, limit: int = 200) -> tuple[NavigationJournalRecord, ...]:
        with self._mutex:
            self._require_open()
            return self._journal.recent(limit=limit)

    def unresolved(self) -> tuple[NavigationJournalRecord, ...]:
        with self._mutex:
            self._require_open()
            return self._journal.unresolved()

    def close(self) -> None:
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            self._backend.close()
