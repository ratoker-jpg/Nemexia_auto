from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from v2.application.browser_readiness import BrowserReadinessError, BrowserReadinessManager
from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.application.spy_actions import (
    SpyActionError,
    SpyActionsDisabled,
    SpyCaptchaBlocked,
    SpyRequestRejected,
    SpyRequestResult,
)
from v2.domain.recon import SpyReportFact
from v2.persistence.automatic_recon_journal import (
    AutomaticReconConflictError,
    AutomaticReconJournalRepository,
)


@dataclass(frozen=True)
class ProcessableSpyFleet:
    fleet_id: str
    source: str
    target: str
    remaining_seconds: int | None

    @property
    def ready(self) -> bool:
        return self.remaining_seconds is not None and self.remaining_seconds <= 0


class AutomaticReconMutationError(SpyActionError):
    """Typed processSpy boundary error with remote-attempt provenance."""

    def __init__(
        self,
        message: str,
        *,
        remote_attempted: bool,
        captcha_present: bool = False,
    ) -> None:
        super().__init__(message)
        self.remote_attempted = bool(remote_attempted)
        self.captcha_present = bool(captcha_present)


class AutomaticReconAmbiguous(SpyActionError):
    """The exact fleet may have been processed; automatic retry is forbidden."""


class AutomaticReconBrowser(Protocol):
    def discover_spy_fleets(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[ProcessableSpyFleet, ...]: ...

    def read_spy_reports(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[SpyReportFact, ...]: ...

    def process_spy_once(
        self,
        *,
        fleet_id: str,
        expected_source: str,
        expected_target: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> None: ...


def select_processable_spy_fleet(
    fleets: tuple[ProcessableSpyFleet, ...],
) -> ProcessableSpyFleet | None:
    """Choose one proven-ready fleet deterministically; never infer missing timers."""

    ready = [item for item in fleets if item.ready]
    if not ready:
        return None

    def key(item: ProcessableSpyFleet) -> tuple[int, str, str, str]:
        numeric = int(item.fleet_id) if item.fleet_id.isdigit() else 2**63 - 1
        return numeric, item.fleet_id, item.source, item.target

    ready.sort(key=key)
    return ready[0]


def select_new_exact_report(
    reports: tuple[SpyReportFact, ...],
    *,
    before_ids: frozenset[str],
    target: str,
    requested_at: datetime,
    clock_tolerance_seconds: int = 30,
) -> SpyReportFact | None:
    threshold = requested_at.astimezone(timezone.utc) - timedelta(
        seconds=max(0, int(clock_tolerance_seconds))
    )
    matches = [
        report
        for report in reports
        if report.report_id
        and report.report_id not in before_ids
        and report.target == target
        and report.reported_at is not None
        and report.reported_at.astimezone(timezone.utc) >= threshold
    ]
    matches.sort(
        key=lambda item: (item.reported_at, item.report_id or ""),
        reverse=True,
    )
    return matches[0] if matches else None


class AutomaticReconService:
    """AUTO-07: one-page, exactly-one automatic exact-fleet recon acquisition."""

    def __init__(
        self,
        browser: AutomaticReconBrowser,
        navigation: NavigationCoordinator,
        journal: AutomaticReconJournalRepository,
        *,
        enabled: bool = False,
    ) -> None:
        self.browser = browser
        self.navigation = navigation
        self.readiness = BrowserReadinessManager(navigation)
        self.journal = journal
        self.enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    @staticmethod
    def _current(observation: NavigationObservation):
        current = observation.identity.current_planet
        if current is None:
            raise SpyRequestRejected("Selected PlanetIdentity is not proven")
        return current

    @classmethod
    def _assert_same_context(
        cls,
        expected: NavigationObservation,
        actual: NavigationObservation,
        *,
        page_kind: str,
    ) -> None:
        expected_planet = cls._current(expected)
        actual_planet = cls._current(actual)
        if actual.page_token != expected.page_token:
            raise SpyRequestRejected("Owned browser page changed during automatic recon")
        if (
            actual.identity.account.ownership_fingerprint
            != expected.identity.account.ownership_fingerprint
        ):
            raise SpyRequestRejected("Account ownership evidence changed during automatic recon")
        if (
            actual_planet.planet_id != expected_planet.planet_id
            or actual_planet.coord != expected_planet.coord
        ):
            raise SpyRequestRejected("Selected PlanetIdentity changed during automatic recon")
        if actual.page.page_kind != page_kind:
            raise SpyRequestRejected(
                f"Expected {page_kind} page during automatic recon, got {actual.page.page_kind}"
            )

    @staticmethod
    def _report_ids(reports: tuple[SpyReportFact, ...]) -> tuple[str, ...]:
        return tuple(sorted({str(item.report_id) for item in reports if item.report_id}))

    @staticmethod
    def _translate_readiness_error(exc: BrowserReadinessError) -> SpyActionError:
        detail = str(exc)
        if "captcha" in detail.casefold():
            return SpyCaptchaBlocked(detail)
        return SpyRequestRejected(detail)

    @staticmethod
    def _translate_read_error(exc: Exception) -> SpyActionError:
        if isinstance(exc, AutomaticReconMutationError):
            if exc.remote_attempted:
                return AutomaticReconAmbiguous(str(exc))
            if exc.captcha_present:
                return SpyCaptchaBlocked(str(exc))
        if isinstance(exc, SpyActionError):
            return exc
        return SpyRequestRejected(f"Automatic recon read preflight failed: {exc}")

    def _preflight_request(self, request_id: str) -> str:
        clean = str(request_id or "").strip()
        if not clean:
            raise SpyRequestRejected("request_id is required for automatic recon")
        if not self.enabled:
            raise SpyActionsDisabled("V2 automatic recon actions are disabled")
        if self.journal.read(clean) is not None:
            raise SpyRequestRejected(f"Automatic recon request already exists: {clean}")
        unresolved = self.journal.unresolved()
        if unresolved:
            item = unresolved[0]
            raise SpyRequestRejected(
                f"Automatic recon blocked by unresolved {item.request_id} ({item.status})"
            )
        manual_unresolved = [
            row
            for row in self.journal.database.list_spy_actions(limit=500)
            if str(row.get("status") or "") in {"pending", "ambiguous"}
        ]
        if manual_unresolved:
            item = manual_unresolved[0]
            raise SpyRequestRejected(
                "Automatic recon blocked by unresolved manual spy request: "
                f"{item['request_id']} ({item['status']})"
            )
        return clean

    def run(self, *, request_id: str) -> SpyRequestResult:
        request_id = self._preflight_request(request_id)

        try:
            self.readiness.ensure_fleets()
        except BrowserReadinessError as exc:
            raise self._translate_readiness_error(exc) from exc

        initial = self.navigation.observe()
        current = self._current(initial)
        self._assert_same_context(initial, initial, page_kind="fleets")
        account = initial.identity.account.ownership_fingerprint

        try:
            fleets = self.browser.discover_spy_fleets(
                expected_planet_id=current.planet_id,
                expected_coord=current.coord,
                expected_account_fingerprint=account,
            )
        except Exception as exc:
            translated = self._translate_read_error(exc)
            raise translated from exc
        chosen = select_processable_spy_fleet(fleets)
        if chosen is None:
            pending = [item.remaining_seconds for item in fleets if item.remaining_seconds is not None]
            suffix = f"; nearest timer={min(pending)}s" if pending else ""
            raise SpyRequestRejected(
                "No processable spy fleet is proven by exact spy1Link/spy1Time DOM" + suffix
            )

        try:
            self.readiness.ensure_messages(planet_coord=current.coord)
        except BrowserReadinessError as exc:
            raise self._translate_readiness_error(exc) from exc
        messages_observation = self.navigation.observe()
        self._assert_same_context(initial, messages_observation, page_kind="options")
        try:
            before_reports = self.browser.read_spy_reports(
                expected_planet_id=current.planet_id,
                expected_coord=current.coord,
                expected_account_fingerprint=account,
            )
        except Exception as exc:
            translated = self._translate_read_error(exc)
            raise translated from exc
        before_ids = frozenset(self._report_ids(before_reports))

        try:
            self.readiness.ensure_fleets(planet_coord=current.coord)
        except BrowserReadinessError as exc:
            raise self._translate_readiness_error(exc) from exc
        fleets_observation = self.navigation.observe()
        self._assert_same_context(initial, fleets_observation, page_kind="fleets")
        try:
            revalidated = {
                item.fleet_id: item
                for item in self.browser.discover_spy_fleets(
                    expected_planet_id=current.planet_id,
                    expected_coord=current.coord,
                    expected_account_fingerprint=account,
                )
            }.get(chosen.fleet_id)
        except Exception as exc:
            translated = self._translate_read_error(exc)
            raise translated from exc
        if (
            revalidated is None
            or not revalidated.ready
            or revalidated.source != chosen.source
            or revalidated.target != chosen.target
        ):
            raise SpyRequestRejected(
                "Chosen spy fleet changed or is no longer processable before journal commit"
            )

        try:
            self.journal.begin(
                request_id=request_id,
                fleet_id=chosen.fleet_id,
                source_coord=chosen.source,
                target_coord=chosen.target,
                account_fingerprint=account,
                planet_id=current.planet_id,
                baseline_keys=tuple(sorted(before_ids)),
            )
        except AutomaticReconConflictError as exc:
            raise SpyRequestRejected(str(exc)) from exc

        requested_at = datetime.now(timezone.utc)
        try:
            self.browser.process_spy_once(
                fleet_id=chosen.fleet_id,
                expected_source=chosen.source,
                expected_target=chosen.target,
                expected_planet_id=current.planet_id,
                expected_coord=current.coord,
                expected_account_fingerprint=account,
            )
        except AutomaticReconMutationError as exc:
            status = "ambiguous" if exc.remote_attempted else "failed_safe"
            self.journal.finish(
                request_id,
                status=status,
                after_keys=None,
                detail=str(exc),
            )
            if exc.remote_attempted:
                raise AutomaticReconAmbiguous(
                    f"{exc}; automatic processSpy retry is forbidden"
                ) from exc
            if exc.captcha_present:
                raise SpyCaptchaBlocked(str(exc)) from exc
            raise SpyRequestRejected(str(exc)) from exc
        except Exception as exc:
            self.journal.finish(
                request_id,
                status="ambiguous",
                after_keys=None,
                detail=str(exc),
            )
            raise AutomaticReconAmbiguous(
                "processSpy result is ambiguous; automatic retry is forbidden"
            ) from exc

        # Match the proven manual/legacy timing without repeating processSpy.
        time.sleep(0.35)
        try:
            self.readiness.ensure_messages(planet_coord=current.coord)
            after_observation = self.navigation.observe()
            self._assert_same_context(initial, after_observation, page_kind="options")
            after_reports = self.browser.read_spy_reports(
                expected_planet_id=current.planet_id,
                expected_coord=current.coord,
                expected_account_fingerprint=account,
            )
        except Exception as exc:
            self.journal.finish(
                request_id,
                status="ambiguous",
                after_keys=None,
                detail=f"Post-process verification failed: {exc}",
            )
            raise AutomaticReconAmbiguous(
                f"Spy fleet may have been processed, but verification failed: {exc}; retry forbidden"
            ) from exc

        after_ids = self._report_ids(after_reports)
        verified = select_new_exact_report(
            after_reports,
            before_ids=before_ids,
            target=chosen.target,
            requested_at=requested_at,
        )
        if verified is None:
            self.journal.finish(
                request_id,
                status="ambiguous",
                after_keys=after_ids,
                detail="No new exact-target fresh report observed; automatic retry forbidden",
            )
            return SpyRequestResult(
                fleet_id=chosen.fleet_id,
                source=chosen.source,
                target=chosen.target,
                requested_at=requested_at,
                verified=False,
                detail="No new exact-target fresh report observed; automatic retry forbidden",
            )

        self.journal.finish(
            request_id,
            status="verified",
            after_keys=after_ids,
            detail="Verified by new exact-target fresh spy report",
        )
        return SpyRequestResult(
            fleet_id=chosen.fleet_id,
            source=chosen.source,
            target=chosen.target,
            requested_at=requested_at,
            verified=True,
            report_id=verified.report_id,
            report_at=verified.reported_at,
            detail="Verified by new exact-target fresh spy report",
        )
