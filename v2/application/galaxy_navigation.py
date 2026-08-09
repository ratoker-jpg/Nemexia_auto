from __future__ import annotations

from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.persistence.navigation_journal import NavigationJournalRecord


class VerifiedGalaxyNavigationCoordinator(NavigationCoordinator):
    """AUTO-09+ central NavigationCoordinator extension."""

    def unresolved(self) -> tuple[NavigationJournalRecord, ...]:
        """Expose persisted unresolved effects to higher-level recovery-safe workflows."""
        return tuple(self._journal.unresolved())

    @staticmethod
    def _galaxy_verified(
        before: NavigationObservation,
        after: NavigationObservation,
        *,
        galaxy: int,
        solar: int,
    ) -> bool:
        return bool(
            NavigationCoordinator._same_context(before, after)
            and after.page.page_kind == "galaxy"
            and after.page.galaxy_ready
            and after.page.galaxy == galaxy
            and after.page.solar == solar
        )

    def navigate_galaxy_system(
        self,
        *,
        request_id: str,
        galaxy: int,
        solar: int,
    ) -> NavigationJournalRecord:
        """Invoke one verified galaxy-system effect for one requested system."""

        galaxy = int(galaxy)
        solar = int(solar)
        with self._mutex:
            self._require_open()
            before = self._backend.observe()
            current = before.identity.current_planet
            self._journal.begin(
                request_id=str(request_id),
                action_kind="galaxy_system",
                before=before.context_dict(),
                intent={
                    "galaxy": galaxy,
                    "solar": solar,
                    "account_fingerprint": before.identity.account.ownership_fingerprint,
                    "planet_id": current.planet_id if current is not None else "",
                    "planet_coord": current.coord if current is not None else "",
                },
            )

            if galaxy < 1 or solar < 1 or solar > 40:
                return self._journal.finish(
                    str(request_id),
                    status="failed_safe",
                    after=before.context_dict(),
                    detail="Galaxy must be >= 1 and solar system must be in range 1..40",
                )
            if current is None or not before.page.galaxy_ready or before.page.page_kind != "galaxy":
                return self._journal.finish(
                    str(request_id),
                    status="failed_safe",
                    after=before.context_dict(),
                    detail="Verified selected PlanetIdentity and ready galaxy.php are required",
                )
            if before.page.galaxy == galaxy and before.page.solar == solar:
                return self._journal.finish(
                    str(request_id),
                    status="verified",
                    after=before.context_dict(),
                    detail="Requested galaxy/system already selected; no remote effect attempted",
                )

            mutate = getattr(self._backend, "navigate_galaxy_system", None)
            if not callable(mutate):
                return self._journal.finish(
                    str(request_id),
                    status="failed_safe",
                    after=before.context_dict(),
                    detail="Galaxy-system navigation backend is unavailable",
                )

            try:
                after = mutate(
                    galaxy=galaxy,
                    solar=solar,
                    expected_planet_id=current.planet_id,
                    expected_coord=current.coord,
                    expected_account_fingerprint=before.identity.account.ownership_fingerprint,
                )
            except Exception as exc:
                return self._finish_mutation_error(
                    request_id=str(request_id),
                    before=before,
                    exc=exc,
                    verified=lambda observed: self._galaxy_verified(
                        before,
                        observed,
                        galaxy=galaxy,
                        solar=solar,
                    ),
                    label=f"Galaxy navigation {galaxy}:{solar}",
                )

            if not self._galaxy_verified(before, after, galaxy=galaxy, solar=solar):
                return self._journal.finish(
                    str(request_id),
                    status="ambiguous",
                    after=after.context_dict(),
                    detail=(
                        "Galaxy refresh returned without full account/planet/page/system verification; "
                        "automatic retry forbidden"
                    ),
                )
            return self._journal.finish(
                str(request_id),
                status="verified",
                after=after.context_dict(),
                detail=f"Galaxy system {galaxy}:{solar} verified on the same owned browser context",
            )
