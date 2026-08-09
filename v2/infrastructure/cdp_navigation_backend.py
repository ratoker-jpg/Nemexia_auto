from __future__ import annotations

from playwright.async_api import Page

from v2.application.navigation import NavigationObservation
from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError


class V2NavigationCdpBackend(ReadOnlyAccountCdpBackend):
    """Own exactly one already-open Nemexia page for future coordinator mutations.

    AUTO-03 is still read-only: this backend binds and observes one runtime Page
    object, but never navigates or invokes any game action. Once bound, page loss
    fails closed instead of silently selecting another tab in the same process.
    """

    def __init__(self, endpoint: str, *, game_host: str = "game.ares.nemexia.com", timeout_seconds: float = 5.0) -> None:
        super().__init__(endpoint, game_host=game_host, timeout_seconds=timeout_seconds, cache_seconds=0.0)
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
        if self._bound_page is None:
            return await self._bind_existing_fleets_page()
        browser = await self._ensure_browser()
        page = self._bound_page
        pages = [item for context in browser.contexts for item in context.pages if not item.is_closed()]
        if page.is_closed() or page not in pages:
            raise CdpReadError(
                "Привязанная Nemexia-вкладка потеряна; автоматическое переподключение к другой вкладке запрещено"
            )
        if self.game_host not in str(page.url) or "fleets.php" not in str(page.url):
            raise CdpReadError(
                "Привязанная вкладка изменила контекст; до AUTO-05 ожидается fleets.php"
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
