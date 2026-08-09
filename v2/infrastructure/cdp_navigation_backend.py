from __future__ import annotations

from playwright.async_api import Page

from v2.application.navigation import NavigationMutationError, NavigationObservation
from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError


class V2NavigationCdpBackend(ReadOnlyAccountCdpBackend):
    """Own one Nemexia page and expose only coordinator-authorized navigation."""

    def __init__(
        self,
        endpoint: str,
        *,
        game_host: str = "game.ares.nemexia.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            endpoint,
            game_host=game_host,
            timeout_seconds=timeout_seconds,
            cache_seconds=0.0,
        )
        self._bound_page: Page | None = None

    async def _bind_existing_fleets_page(self) -> Page:
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        candidates = [
            page for page in pages
            if self.game_host in str(page.url) and "fleets.php" in str(page.url)
        ]
        if not candidates:
            raise CdpReadError("Открой ровно одну fleets.php вкладку для привязки NavigationCoordinator")
        if len(candidates) != 1:
            raise CdpReadError(
                f"Найдено несколько fleets.php вкладок ({len(candidates)}); "
                "NavigationCoordinator не выбирает вкладку неоднозначно"
            )
        self._bound_page = candidates[0]
        return candidates[0]

    async def _existing_fleets_page(self) -> Page:
        """Return the navigation-owned page.

        Initial binding still requires fleets.php. After the coordinator performs a
        verified navigation the same Page object may legitimately have another
        Nemexia URL, so ownership is page-object + game-host, not path equality.
        """

        if self._bound_page is None:
            return await self._bind_existing_fleets_page()
        browser = await self._ensure_browser()
        page = self._bound_page
        pages = [item for context in browser.contexts for item in context.pages if not item.is_closed()]
        if page.is_closed() or page not in pages:
            raise CdpReadError(
                "Привязанная Nemexia-вкладка потеряна; автоматическое переподключение к другой вкладке запрещено"
            )
        if self.game_host not in str(page.url):
            raise CdpReadError(
                "Привязанная вкладка покинула Nemexia; автоматическое продолжение запрещено"
            )
        return page

    async def _observe(self) -> NavigationObservation:
        page = await self._existing_fleets_page()
        identity = await self._read_browser_identity()
        return NavigationObservation(
            page_token=f"runtime-page:{id(page)}",
            identity=identity,
        )

    def observe(self) -> NavigationObservation:
        return self._submit(self._observe())

    async def _switch_planet(
        self,
        *,
        planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        try:
            page = await self._existing_fleets_page()
            href = await page.evaluate(
                r"""args => {
                    const [planetId, coord, host] = args;
                    for (const a of Array.from(document.querySelectorAll('#planetsListHolder a'))) {
                        let url;
                        try { url = new URL(a.getAttribute('href') || '', location.href); }
                        catch (_) { continue; }
                        if (url.hostname !== host) continue;
                        if (!url.pathname.endsWith('/change_planet.php')) continue;
                        if ((url.searchParams.get('id') || '') !== String(planetId)) continue;
                        const text=(a.textContent||'').replace(/\s+/g,'');
                        if (!text.includes('[' + coord + ']')) continue;
                        return url.href;
                    }
                    return '';
                }""",
                [str(planet_id), str(expected_coord), self.game_host],
            )
        except Exception as exc:
            raise NavigationMutationError(
                f"Planet switch preflight failed before remote mutation: {exc}",
                remote_attempted=False,
            ) from exc
        if not href:
            raise NavigationMutationError(
                "PlanetIdentity no longer matches an owned change_planet.php anchor",
                remote_attempted=False,
            )

        # Exactly one remote navigation attempt. Any exception after this point is
        # tagged as post-attempt so the coordinator can only reconcile or persist
        # ambiguity; it must never issue a second navigation automatically.
        try:
            await page.goto(
                href,
                wait_until="domcontentloaded",
                timeout=int(self.timeout_seconds * 1000),
            )
            await page.locator("#planetSwitch").wait_for(
                state="attached",
                timeout=int(self.timeout_seconds * 1000),
            )
            identity = await self._read_browser_identity()
            if identity.account.ownership_fingerprint != str(expected_account_fingerprint):
                raise CdpReadError("Account ownership evidence changed after planet switch")
            current = identity.current_planet
            if current is None or current.planet_id != str(planet_id) or current.coord != str(expected_coord):
                raise CdpReadError("Selected planet proof does not match the requested PlanetIdentity")
        except Exception as exc:
            raise NavigationMutationError(
                f"Planet switch failed after remote navigation started: {exc}",
                remote_attempted=True,
            ) from exc
        return NavigationObservation(
            page_token=f"runtime-page:{id(page)}",
            identity=identity,
        )

    def switch_planet(
        self,
        *,
        planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        return self._submit(
            self._switch_planet(
                planet_id=planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )
