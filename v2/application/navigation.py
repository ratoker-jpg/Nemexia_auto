from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping, Protocol

from v2.application.browser_identity import BrowserIdentitySnapshot, PlanetIdentity
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

    def switch_planet(
        self,
        *,
        planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation: ...

    def close(self) -> None: ...


class NavigationCoordinator:
    """Serialize browser context ownership and persistent exactly-one mutations."""

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

    @staticmethod
    def _switch_verified(
        before: NavigationObservation,
        after: NavigationObservation,
        target: PlanetIdentity,
    ) -> bool:
        current = after.identity.current_planet
        return bool(
            after.page_token == before.page_token
            and after.identity.session.server_host == before.identity.session.server_host
            and after.identity.account.ownership_fingerprint
            == before.identity.account.ownership_fingerprint
            == target.account_fingerprint
            and current is not None
            and current.selected
            and current.planet_id == target.planet_id
            and current.coord == target.coord
        )

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
        """Persist immutable intent before a future remote context mutation."""

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

    def switch_planet(self, *, request_id: str, planet_id: str) -> NavigationJournalRecord:
        """Switch once to one proven owned planet and verify the full context.

        The remote backend is invoked at most once. Any exception or mismatching
        after-state is reconciled only from read evidence and otherwise persisted
        as ``ambiguous``; this method never performs an automatic retry.
        """

        with self._mutex:
            self._require_open()
            before = self._backend.observe()
            target = before.identity.by_id(str(planet_id))
            intent = {"planet_id": str(planet_id)}
            if target is not None:
                intent.update(
                    {
                        "planet_coord": target.coord,
                        "account_fingerprint": target.account_fingerprint,
                    }
                )
            self._journal.begin(
                request_id=request_id,
                action_kind="switch_planet",
                before=before.context_dict(),
                intent=intent,
            )
            if target is None:
                return self._journal.finish(
                    request_id,
                    status="failed_safe",
                    after=before.context_dict(),
                    detail="Requested planet is not present in the proven owned-planet set",
                )
            if before.identity.current_planet is not None and before.identity.current_planet.planet_id == target.planet_id:
                return self._journal.finish(
                    request_id,
                    status="verified",
                    after=before.context_dict(),
                    detail="Target planet was already selected; no remote mutation attempted",
                )

            try:
                after = self._backend.switch_planet(
                    planet_id=target.planet_id,
                    expected_coord=target.coord,
                    expected_account_fingerprint=target.account_fingerprint,
                )
            except Exception as exc:
                try:
                    observed = self._backend.observe()
                except Exception:
                    observed = None
                if observed is not None and self._switch_verified(before, observed, target):
                    return self._journal.finish(
                        request_id,
                        status="verified",
                        after=observed.context_dict(),
                        detail=f"Planet switch verified by read reconciliation after backend error: {exc}",
                    )
                return self._journal.finish(
                    request_id,
                    status="ambiguous",
                    after=observed.context_dict() if observed is not None else None,
                    detail=f"Planet switch remote effect is uncertain; automatic retry forbidden: {exc}",
                )

            if not self._switch_verified(before, after, target):
                return self._journal.finish(
                    request_id,
                    status="ambiguous",
                    after=after.context_dict(),
                    detail="Planet switch returned but account/page/selected-planet verification did not match",
                )
            return self._journal.finish(
                request_id,
                status="verified",
                after=after.context_dict(),
                detail="Planet switch verified by page token, account fingerprint, internal ID and coordinate",
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
