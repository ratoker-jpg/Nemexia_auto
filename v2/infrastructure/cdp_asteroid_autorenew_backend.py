from __future__ import annotations

from v2.application.asteroid_actions import AsteroidActionError
from v2.infrastructure.cdp_mutation_sessions import V2AsteroidCdpBackendNoAutoReconnect


class V2AutorenewAsteroidCdpBackendNoAutoReconnect(V2AsteroidCdpBackendNoAutoReconnect):
    """Existing asteroid SendFleet backend without the obsolete second-tab prerequisite.

    `V2AsteroidCdpBackend._recheck_observation()` needs only a same-origin page on
    which it can read `window.currentTime` and POST explicit coordinates to the
    read-only `ajax_info.php type=squareInfo` endpoint. The original attach-only
    batch required a simultaneously open matching galaxy tab because browser
    preparation had not yet been centralized.

    AUTO-11 prepares/proves galaxy evidence first through NavigationCoordinator,
    then prepares the same owned tab as fleets.php. Returning that proven fleets
    page here keeps the independent pre-send squareInfo trajectory re-check while
    reusing the exact existing SendFleet implementation unchanged.
    """

    async def _matching_galaxy_page(self, galaxy: int, system: int):
        page = await self._existing_fleets_page()
        if await self._captcha_present(page):
            raise AsteroidActionError(
                "CAPTCHA detected before autorenew asteroid trajectory re-check"
            )
        return page

    async def _autorenew_captcha_present(self) -> bool:
        page = await self._existing_fleets_page()
        return bool(await self._captcha_present(page))

    def autorenew_captcha_present(self) -> bool:
        return bool(self._action_submit(self._autorenew_captcha_present()))
