from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Page

from v2.application.navigation import (
    NavigationMutationError,
    NavigationObservation,
    NavigationPageState,
)
from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError


_PAGE_PATHS = {
    "fleets": "/fleets.php",
    "options": "/options.php",
    "galaxy": "/galaxy.php",
}


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

    def _is_game_page(self, page: Page) -> bool:
        return (urlsplit(str(page.url)).hostname or "").casefold() == self.game_host.casefold()

    async def _bind_existing_game_page(self) -> Page:
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        candidates = [page for page in pages if self._is_game_page(page)]
        if not candidates:
            raise CdpReadError(
                "Открой одну авторизованную Nemexia-вкладку для привязки NavigationCoordinator"
            )
        if len(candidates) != 1:
            raise CdpReadError(
                f"Найдено несколько Nemexia-вкладок ({len(candidates)}); "
                "NavigationCoordinator не выбирает вкладку неоднозначно"
            )
        self._bound_page = candidates[0]
        return candidates[0]

    async def _existing_bound_page(self) -> Page:
        if self._bound_page is None:
            return await self._bind_existing_game_page()
        browser = await self._ensure_browser()
        page = self._bound_page
        pages = [item for context in browser.contexts for item in context.pages if not item.is_closed()]
        if page.is_closed() or page not in pages:
            raise CdpReadError(
                "Привязанная Nemexia-вкладка потеряна; автоматическое переподключение к другой вкладке запрещено"
            )
        if not self._is_game_page(page):
            raise CdpReadError(
                "Привязанная вкладка покинула Nemexia; автоматическое продолжение запрещено"
            )
        return page

    async def _existing_fleets_page(self) -> Page:
        """Compatibility hook used by the account reader on the bound game page."""

        return await self._existing_bound_page()

    async def _read_page_state(self, page: Page) -> NavigationPageState:
        try:
            raw = await page.evaluate(
                r"""() => {
                    const url=new URL(location.href);
                    const path=url.pathname.toLowerCase();
                    const fleets=path.endsWith('/fleets.php')
                        && !!document.querySelector('#FleetsCount')
                        && !!document.querySelector('#MaxFleets');
                    const options=path.endsWith('/options.php')
                        && !!document.querySelector('#messagesFolders');
                    const admin=document.querySelector('#TabAdministrative');
                    const adminBox=document.querySelector('#TabAdministrativeBox');
                    const adminTitle=(admin?.querySelector('h1')?.textContent || '').toLowerCase();
                    const messages=options && !!(
                        adminBox?.querySelector('#messagesList')
                        || admin?.querySelector('#messagesList')
                        || admin?.querySelector('.messageItem')
                        || adminBox?.querySelector('.messageItem')
                        || adminTitle.includes('систем')
                        || adminTitle.includes('system')
                    );
                    const c1=Number(document.querySelector('#c1')?.value || 0);
                    const c2=Number(document.querySelector('#c2')?.value || 0);
                    const galaxy=path.endsWith('/galaxy.php')
                        && !!document.querySelector('#galaxyHolder')
                        && c1>0 && c2>0;
                    let kind='other';
                    if(path.endsWith('/fleets.php')) kind='fleets';
                    else if(path.endsWith('/options.php')) kind='options';
                    else if(path.endsWith('/galaxy.php')) kind='galaxy';
                    return {
                        page_kind:kind,
                        fleets_ready:fleets,
                        options_ready:options,
                        messages_ready:messages,
                        galaxy_ready:galaxy,
                        galaxy:c1>0 ? c1 : null,
                        solar:c2>0 ? c2 : null
                    };
                }"""
            )
        except Exception as exc:
            raise CdpReadError("Не удалось прочитать readiness текущей Nemexia-страницы") from exc
        return NavigationPageState(
            page_kind=str(raw.get("page_kind") or "unknown"),
            fleets_ready=bool(raw.get("fleets_ready")),
            options_ready=bool(raw.get("options_ready")),
            messages_ready=bool(raw.get("messages_ready")),
            galaxy_ready=bool(raw.get("galaxy_ready")),
            galaxy=int(raw["galaxy"]) if raw.get("galaxy") is not None else None,
            solar=int(raw["solar"]) if raw.get("solar") is not None else None,
        )

    async def _observe(self) -> NavigationObservation:
        page = await self._existing_bound_page()
        identity = await self._read_browser_identity()
        page_state = await self._read_page_state(page)
        return NavigationObservation(
            page_token=f"runtime-page:{id(page)}",
            identity=identity,
            page=page_state,
        )

    def observe(self) -> NavigationObservation:
        return self._submit(self._observe())

    async def _validate_expected_context(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> Page:
        page = await self._existing_bound_page()
        identity = await self._read_browser_identity()
        current = identity.current_planet
        if identity.account.ownership_fingerprint != str(expected_account_fingerprint):
            raise CdpReadError("Account ownership evidence changed before navigation")
        if current is None or current.planet_id != str(expected_planet_id) or current.coord != str(expected_coord):
            raise CdpReadError("Selected PlanetIdentity changed before navigation")
        return page

    async def _navigate_once(self, page: Page, url: str, *, label: str) -> None:
        """Perform the single remote page navigation attempt for one journal request."""

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.timeout_seconds * 1000),
            )
        except Exception as exc:
            raise NavigationMutationError(
                f"{label} failed after remote navigation started: {exc}",
                remote_attempted=True,
            ) from exc

    async def _switch_planet(
        self,
        *,
        planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        try:
            page = await self._validate_expected_context(
                expected_planet_id=(await self._read_browser_identity()).current_planet.planet_id
                if (await self._read_browser_identity()).current_planet is not None
                else "",
                expected_coord=(await self._read_browser_identity()).current_planet.coord
                if (await self._read_browser_identity()).current_planet is not None
                else "",
                expected_account_fingerprint=expected_account_fingerprint,
            )
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
            if isinstance(exc, NavigationMutationError):
                raise
            raise NavigationMutationError(
                f"Planet switch preflight failed before remote mutation: {exc}",
                remote_attempted=False,
            ) from exc
        if not href:
            raise NavigationMutationError(
                "PlanetIdentity no longer matches an owned change_planet.php anchor",
                remote_attempted=False,
            )

        await self._navigate_once(page, href, label="Planet switch")
        try:
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
            page_state = await self._read_page_state(page)
        except Exception as exc:
            raise NavigationMutationError(
                f"Planet switch verification failed after remote navigation: {exc}",
                remote_attempted=True,
            ) from exc
        return NavigationObservation(
            page_token=f"runtime-page:{id(page)}",
            identity=identity,
            page=page_state,
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

    async def _prepare_page(
        self,
        *,
        page_kind: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        path = _PAGE_PATHS.get(str(page_kind))
        if path is None:
            raise NavigationMutationError(
                f"Unsupported page preparation target: {page_kind}",
                remote_attempted=False,
            )
        try:
            page = await self._validate_expected_context(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
            parts = urlsplit(str(page.url))
            target_url = urlunsplit((parts.scheme or "https", parts.netloc, path, "", ""))
        except Exception as exc:
            if isinstance(exc, NavigationMutationError):
                raise
            raise NavigationMutationError(
                f"Prepare {page_kind} preflight failed before remote navigation: {exc}",
                remote_attempted=False,
            ) from exc

        await self._navigate_once(page, target_url, label=f"Prepare {page_kind}")
        try:
            await page.locator("#planetSwitch").wait_for(
                state="attached",
                timeout=int(self.timeout_seconds * 1000),
            )
            return await self._observe()
        except Exception as exc:
            raise NavigationMutationError(
                f"Prepare {page_kind} verification failed after remote navigation: {exc}",
                remote_attempted=True,
            ) from exc

    def prepare_page(
        self,
        *,
        page_kind: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        return self._submit(
            self._prepare_page(
                page_kind=page_kind,
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )

    async def _prepare_system_messages(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        try:
            page = await self._validate_expected_context(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
            state = await self._read_page_state(page)
            if not state.options_ready:
                raise CdpReadError("options.php shell is not ready")
            callable_loader = await page.evaluate(
                "() => typeof window.loadTabContent === 'function'"
            )
            if not callable_loader:
                raise CdpReadError("loadTabContent is unavailable on options.php")
        except Exception as exc:
            raise NavigationMutationError(
                f"System messages preflight failed before remote content load: {exc}",
                remote_attempted=False,
            ) from exc

        try:
            await page.evaluate(
                r"""() => {
                    window.loadTabContent('TabAdministrative', 2, 0);
                    if (typeof window.showTab === 'function') window.showTab('TabAdministrative');
                }"""
            )
            await page.wait_for_function(
                r"""() => {
                    const admin=document.querySelector('#TabAdministrative');
                    const box=document.querySelector('#TabAdministrativeBox');
                    const title=(admin?.querySelector('h1')?.textContent || '').toLowerCase();
                    return !!(
                        box?.querySelector('#messagesList')
                        || admin?.querySelector('#messagesList')
                        || admin?.querySelector('.messageItem')
                        || box?.querySelector('.messageItem')
                        || title.includes('систем')
                        || title.includes('system')
                    );
                }""",
                timeout=int(self.timeout_seconds * 1000),
            )
            return await self._observe()
        except Exception as exc:
            raise NavigationMutationError(
                f"System messages failed after remote content load started: {exc}",
                remote_attempted=True,
            ) from exc

    def prepare_system_messages(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        return self._submit(
            self._prepare_system_messages(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )
