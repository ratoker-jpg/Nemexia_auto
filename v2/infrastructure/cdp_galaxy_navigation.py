from __future__ import annotations

from v2.application.navigation import NavigationMutationError, NavigationObservation


class VerifiedGalaxyNavigationMixin:
    """One exactly-once refreshGalaxy effect over the already owned galaxy page."""

    async def _navigate_galaxy_system(
        self,
        *,
        galaxy: int,
        solar: int,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        galaxy = int(galaxy)
        solar = int(solar)
        if galaxy < 1 or solar < 1 or solar > 40:
            raise NavigationMutationError(
                "Galaxy must be >= 1 and solar system must be in range 1..40",
                remote_attempted=False,
            )

        try:
            page = await self._validate_expected_context(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
            state = await self._read_page_state(page)
            if state.page_kind != "galaxy" or not state.galaxy_ready:
                raise RuntimeError("Verified galaxy.php readiness is required")
            captcha = getattr(self, "_captcha_present", None)
            if callable(captcha) and await captcha(page):
                raise RuntimeError("CAPTCHA detected before galaxy navigation")
            preflight = await page.evaluate(
                """() => ({
                    c1: !!document.querySelector('#c1'),
                    c2: !!document.querySelector('#c2'),
                    holder: !!document.querySelector('#galaxyHolder'),
                    refresh: typeof window.refreshGalaxy === 'function'
                })"""
            )
            if not all(bool(preflight.get(key)) for key in ("c1", "c2", "holder", "refresh")):
                raise RuntimeError("Galaxy refresh controls are not ready")
            before_html = await page.locator("#galaxyHolder").inner_html()
        except NavigationMutationError:
            raise
        except Exception as exc:
            raise NavigationMutationError(
                f"Galaxy navigation preflight failed: {exc}",
                remote_attempted=False,
            ) from exc

        try:
            async with page.expect_response(
                lambda response: "ajax_galaxy.php" in response.url
                and response.request.method == "POST",
                timeout=20_000,
            ):
                await page.evaluate(
                    """args => {
                        const [g,s]=args;
                        document.querySelector('#c1').value=String(g);
                        document.querySelector('#c2').value=String(s);
                        window.refreshGalaxy();
                    }""",
                    [galaxy, solar],
                )

            try:
                await page.wait_for_function(
                    """args => {
                        const [g,s,before]=args;
                        const holder=document.querySelector('#galaxyHolder');
                        const loading=document.querySelector('#galaxyLoading');
                        if(!holder) return false;
                        const hidden=!loading || getComputedStyle(loading).display==='none';
                        return document.querySelector('#c1')?.value===String(g)
                            && document.querySelector('#c2')?.value===String(s)
                            && hidden && holder.innerHTML.trim() && holder.innerHTML!==before;
                    }""",
                    arg=[galaxy, solar, before_html],
                    timeout=20_000,
                )
            except Exception:
                await page.wait_for_function(
                    """args => {
                        const [g,s]=args;
                        const holder=document.querySelector('#galaxyHolder');
                        const loading=document.querySelector('#galaxyLoading');
                        return document.querySelector('#c1')?.value===String(g)
                            && document.querySelector('#c2')?.value===String(s)
                            && holder?.innerHTML.trim()
                            && (!loading || getComputedStyle(loading).display==='none');
                    }""",
                    arg=[galaxy, solar],
                    timeout=8_000,
                )
            if callable(captcha) and await captcha(page):
                raise RuntimeError("CAPTCHA detected after galaxy navigation")
            return await self._observe()
        except Exception as exc:
            raise NavigationMutationError(
                f"refreshGalaxy({galaxy}:{solar}) was attempted but verification is uncertain: {exc}",
                remote_attempted=True,
            ) from exc

    def navigate_galaxy_system(
        self,
        *,
        galaxy: int,
        solar: int,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> NavigationObservation:
        return self._submit(
            self._navigate_galaxy_system(
                galaxy=galaxy,
                solar=solar,
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )
