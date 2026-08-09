from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from v2.application.browser_identity import BrowserIdentitySnapshot, PlanetIdentity
from v2.persistence.navigation_journal import (
    NavigationJournalRecord,
    NavigationJournalRepository,
)


class NavigationMutationError(RuntimeError):
    """Browser-context mutation error with explicit remote-attempt provenance."""

    def __init__(self, message: str, *, remote_attempted: bool) -> None:
        super().__init__(message)
        self.remote_attempted = bool(remote_attempted)


@dataclass(frozen=True)
class NavigationPageState:
    page_kind: str = "unknown"
    fleets_ready: bool = False
    options_ready: bool = False
    messages_ready: bool = False
    galaxy_ready: bool = False
    galaxy: int | None = None
    solar: int | None = None


@dataclass(frozen=True)
class NavigationObservation:
    """Exact in-process page ownership plus account/planet/page readiness evidence."""

    page_token: str
    identity: BrowserIdentitySnapshot
    page: NavigationPageState = field(default_factory=NavigationPageState)

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
            "page_kind": self.page.page_kind,
            "fleets_ready": self.page.fleets_ready,
            "options_ready": self.page.options_ready,
            "messages_ready": self.page.messages_ready,
            "galaxy_ready": self.page.galaxy_ready,
            "galaxy": self.page.galaxy,
            "solar": self.page.solar,
        }


@dataclass(frozen=True)
class MessagePreparationResult:
    page: NavigationJournalRecord
    system_tab: NavigationJournalRecord | None

    @property
    def verified(self) -> bool:
        return bool(
            self.page.status == "verified"
            and self.system_tab is not None
            and self.system_tab.status == "verified"
        )


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

    def prepare_page(
        self,
        *,
        page_kind: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation: ...

    def prepare_system_messages(
        self,
        *,
        expected_planet_id: str,
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
    def _same_context(before: NavigationObservation, after: NavigationObservation) -> bool:
        before_planet = before.identity.current_planet
        after_planet = after.identity.current_planet
        return bool(
            before_planet is not None
            and after_planet is not None
            and before.page_token == after.page_token
            and before.identity.session.server_host == after.identity.session.server_host
            and before.identity.account.ownership_fingerprint
            == after.identity.account.ownership_fingerprint
            and before_planet.planet_id == after_planet.planet_id
            and before_planet.coord == after_planet.coord
        )

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

    @staticmethod
    def _page_ready(observation: NavigationObservation, page_kind: str) -> bool:
        if page_kind == "fleets":
            return observation.page.fleets_ready
        if page_kind == "options":
            return observation.page.options_ready
        if page_kind == "galaxy":
            return observation.page.galaxy_ready
        if page_kind == "messages":
            return observation.page.messages_ready
        return False

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

    def _finish_mutation_error(
        self,
        *,
        request_id: str,
        before: NavigationObservation,
        exc: Exception,
        verified,
        label: str,
    ) -> NavigationJournalRecord:
        try:
            observed = self._backend.observe()
        except Exception:
            observed = None
        if isinstance(exc, NavigationMutationError) and not exc.remote_attempted:
            return self._journal.finish(
                request_id,
                status="failed_safe",
                after=observed.context_dict() if observed is not None else before.context_dict(),
                detail=f"{label} blocked before remote effect: {exc}",
            )
        if observed is not None and verified(observed):
            return self._journal.finish(
                request_id,
                status="verified",
                after=observed.context_dict(),
                detail=f"{label} verified by read reconciliation after backend error: {exc}",
            )
        return self._journal.finish(
            request_id,
            status="ambiguous",
            after=observed.context_dict() if observed is not None else None,
            detail=f"{label} remote effect is uncertain; automatic retry forbidden: {exc}",
        )

    def switch_planet(self, *, request_id: str, planet_id: str) -> NavigationJournalRecord:
        """Switch once to one proven owned planet and verify the full context."""

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
                return self._finish_mutation_error(
                    request_id=request_id,
                    before=before,
                    exc=exc,
                    verified=lambda observed: self._switch_verified(before, observed, target),
                    label="Planet switch",
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

    def _prepare_page(
        self,
        *,
        request_id: str,
        action_kind: str,
        page_kind: str,
        phase: str = "page",
    ) -> NavigationJournalRecord:
        before = self._backend.observe()
        current = before.identity.current_planet
        self._journal.begin(
            request_id=request_id,
            action_kind=action_kind,
            before=before.context_dict(),
            intent={
                "page_kind": page_kind,
                "phase": phase,
                "account_fingerprint": before.identity.account.ownership_fingerprint,
                "planet_id": current.planet_id if current is not None else "",
                "planet_coord": current.coord if current is not None else "",
            },
        )
        if current is None:
            return self._journal.finish(
                request_id,
                status="failed_safe",
                after=before.context_dict(),
                detail=f"Cannot prepare {page_kind}: selected PlanetIdentity is not proven",
            )
        if self._page_ready(before, page_kind):
            return self._journal.finish(
                request_id,
                status="verified",
                after=before.context_dict(),
                detail=f"{page_kind} was already ready; no remote navigation attempted",
            )

        try:
            after = self._backend.prepare_page(
                page_kind=page_kind,
                expected_planet_id=current.planet_id,
                expected_coord=current.coord,
                expected_account_fingerprint=before.identity.account.ownership_fingerprint,
            )
        except Exception as exc:
            return self._finish_mutation_error(
                request_id=request_id,
                before=before,
                exc=exc,
                verified=lambda observed: self._same_context(before, observed)
                and self._page_ready(observed, page_kind),
                label=f"Prepare {page_kind}",
            )

        if not self._same_context(before, after) or not self._page_ready(after, page_kind):
            return self._journal.finish(
                request_id,
                status="ambiguous",
                after=after.context_dict(),
                detail=f"{page_kind} preparation returned without full account/planet/page verification",
            )
        return self._journal.finish(
            request_id,
            status="verified",
            after=after.context_dict(),
            detail=f"{page_kind} prepared and account/planet/page context verified",
        )

    def prepare_fleets(self, *, request_id: str) -> NavigationJournalRecord:
        with self._mutex:
            self._require_open()
            return self._prepare_page(
                request_id=request_id,
                action_kind="prepare_fleets",
                page_kind="fleets",
            )

    def prepare_galaxy(self, *, request_id: str) -> NavigationJournalRecord:
        with self._mutex:
            self._require_open()
            return self._prepare_page(
                request_id=request_id,
                action_kind="prepare_galaxy",
                page_kind="galaxy",
            )

    def prepare_system_messages(self, *, request_id: str) -> MessagePreparationResult:
        """Prepare Options then System messages as two separately journaled effects."""

        with self._mutex:
            self._require_open()
            page_record = self._prepare_page(
                request_id=request_id,
                action_kind="prepare_messages",
                page_kind="options",
                phase="options_page",
            )
            if page_record.status != "verified":
                return MessagePreparationResult(page_record, None)

            tab_request_id = f"{request_id}:system-tab"
            before = self._backend.observe()
            current = before.identity.current_planet
            self._journal.begin(
                request_id=tab_request_id,
                action_kind="prepare_messages",
                before=before.context_dict(),
                intent={
                    "page_kind": "messages",
                    "phase": "system_tab",
                    "account_fingerprint": before.identity.account.ownership_fingerprint,
                    "planet_id": current.planet_id if current is not None else "",
                    "planet_coord": current.coord if current is not None else "",
                },
            )
            if current is None or not before.page.options_ready:
                tab_record = self._journal.finish(
                    tab_request_id,
                    status="failed_safe",
                    after=before.context_dict(),
                    detail="System messages require a verified selected planet and options.php shell",
                )
                return MessagePreparationResult(page_record, tab_record)
            if before.page.messages_ready:
                tab_record = self._journal.finish(
                    tab_request_id,
                    status="verified",
                    after=before.context_dict(),
                    detail="System messages were already rendered; no remote content load attempted",
                )
                return MessagePreparationResult(page_record, tab_record)

            try:
                after = self._backend.prepare_system_messages(
                    expected_planet_id=current.planet_id,
                    expected_coord=current.coord,
                    expected_account_fingerprint=before.identity.account.ownership_fingerprint,
                )
            except Exception as exc:
                tab_record = self._finish_mutation_error(
                    request_id=tab_request_id,
                    before=before,
                    exc=exc,
                    verified=lambda observed: self._same_context(before, observed)
                    and observed.page.messages_ready,
                    label="Prepare System messages",
                )
                return MessagePreparationResult(page_record, tab_record)

            if not self._same_context(before, after) or not after.page.messages_ready:
                tab_record = self._journal.finish(
                    tab_request_id,
                    status="ambiguous",
                    after=after.context_dict(),
                    detail="System messages load returned without full account/planet/readiness verification",
                )
            else:
                tab_record = self._journal.finish(
                    tab_request_id,
                    status="verified",
                    after=after.context_dict(),
                    detail="System messages rendered and account/planet/page context verified",
                )
            return MessagePreparationResult(page_record, tab_record)

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
