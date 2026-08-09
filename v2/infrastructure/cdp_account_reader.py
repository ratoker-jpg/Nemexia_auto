from __future__ import annotations

from v2.application.browser_identity import (
    BrowserIdentityError,
    BrowserIdentitySnapshot,
    PlanetDomFact,
    build_browser_identity,
)
from v2.application.report_source import BrowserReportStatus, BrowserSpyReportSnapshot
from v2.infrastructure.cdp_read_backend import CdpReadError, ReadOnlyCdpBackend, extract_coord
from v2.infrastructure.spy_report_parser import parse_rendered_spy_reports


class ReadOnlyAccountCdpBackend(ReadOnlyCdpBackend):
    """Extend attach-only fleet reads with typed account/planet and report facts.

    The reader only inspects DOM from pages already open in the connected browser.
    It never follows links, switches planets, creates tabs, loads message tabs or
    navigates to another game page.
    """

    async def _read_browser_identity(self) -> BrowserIdentitySnapshot:
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        game_pages = [page for page in pages if self.game_host in str(page.url)]
        page = await self._existing_fleets_page()
        try:
            raw = await page.evaluate(
                r"""() => {
                    const bodyText=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                    const lower=bodyText.toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    const captcha=recaptcha || botLock || [
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ].some(value => lower.includes(value));
                    const triggerText=document.querySelector('#planetSwitch .trigger big')?.textContent || '';
                    const triggerMatch=triggerText.match(/\[(\d+)\s*:\s*(\d+)\s*:\s*(\d+)\]/);
                    const planets=Array.from(document.querySelectorAll('#planetsListHolder a')).map(a => {
                        let url;
                        try { url=new URL(a.getAttribute('href')||'', location.href); } catch (_) { return null; }
                        if (!url.pathname.endsWith('/change_planet.php')) return null;
                        const planetId=url.searchParams.get('id')||'';
                        const text=(a.textContent||'').replace(/\s+/g,' ').trim();
                        const coordMatch=text.match(/\[(\d+)\s*:\s*(\d+)\s*:\s*(\d+)\]/);
                        if (!planetId || !coordMatch) return null;
                        const coord=[coordMatch[1],coordMatch[2],coordMatch[3]].join(':');
                        const name=text.replace(coordMatch[0], '').replace(/\s+/g,' ').trim();
                        return {
                            planet_id:planetId,
                            coord,
                            display_name:name,
                            selected_by_list:!!a.closest('li')?.classList.contains('active')
                        };
                    }).filter(Boolean);
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        trigger_coord:triggerMatch ? [triggerMatch[1],triggerMatch[2],triggerMatch[3]].join(':') : '',
                        planets
                    };
                }"""
            )
        except Exception as exc:
            raise CdpReadError("Не удалось прочитать BrowserSession/AccountContext/PlanetIdentity") from exc
        if bool(raw.get("captcha_present")):
            raise CdpReadError("CAPTCHA обнаружена — identity read остановлен")
        facts = tuple(
            PlanetDomFact(
                planet_id=str(item.get("planet_id") or ""),
                coord=str(item.get("coord") or ""),
                display_name=str(item.get("display_name") or ""),
                selected_by_list=bool(item.get("selected_by_list")),
            )
            for item in (raw.get("planets") or [])
        )
        try:
            return build_browser_identity(
                endpoint=self.endpoint,
                page_url=str(raw.get("page_url") or page.url),
                page_count=len(pages),
                game_page_count=len(game_pages),
                planets=facts,
                trigger_coord=str(raw.get("trigger_coord") or "") or None,
            )
        except BrowserIdentityError as exc:
            raise CdpReadError(str(exc)) from exc

    def browser_identity(self) -> BrowserIdentitySnapshot:
        """Return typed read-only identity; no browser mutation is performed."""

        return self._submit(self._read_browser_identity())

    async def _read_owned_planets(self) -> tuple[str, ...]:
        identity = await self._read_browser_identity()
        return tuple(planet.coord for planet in identity.planets)

    def owned_planets(self) -> tuple[str, ...]:
        try:
            return tuple(planet.coord for planet in self.browser_identity().planets)
        except CdpReadError:
            return ()

    async def _existing_options_page(self):
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        page = next(
            (
                item
                for item in pages
                if self.game_host in item.url and "options.php" in item.url
            ),
            None,
        )
        if page is None:
            raise CdpReadError("Открой options.php и раздел системных сообщений в подключённом браузере")
        return page

    async def _read_spy_report_dom(self) -> dict[str, object]:
        page = await self._existing_options_page()
        try:
            raw = await page.evaluate(
                r"""() => {
                    const bodyText=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                    const lower=bodyText.toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    const phrases=[
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ];
                    const captcha=recaptcha || botLock || phrases.some(value => lower.includes(value));
                    const box=document.querySelector('#TabAdministrativeBox');
                    const list=box?.querySelector('#messagesList');
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        ready:!!list,
                        html:box?.innerHTML||''
                    };
                }"""
            )
        except Exception as exc:
            raise CdpReadError("Не удалось прочитать DOM системных сообщений") from exc
        return {
            "page_url": str(raw.get("page_url") or page.url),
            "captcha_present": bool(raw.get("captcha_present")),
            "ready": bool(raw.get("ready")),
            "html": str(raw.get("html") or ""),
        }

    def read_spy_reports(self) -> BrowserSpyReportSnapshot:
        """Read only the already-rendered administrative message list."""

        try:
            raw = self._submit(self._read_spy_report_dom())
        except CdpReadError as exc:
            return BrowserSpyReportSnapshot(
                BrowserReportStatus(False, endpoint=self.endpoint, detail=str(exc))
            )

        page_url = str(raw.get("page_url") or "")
        if bool(raw.get("captcha_present")):
            return BrowserSpyReportSnapshot(
                BrowserReportStatus(
                    False,
                    captcha_present=True,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="CAPTCHA обнаружена — чтение разведданных остановлено",
                )
            )
        if not bool(raw.get("ready")):
            return BrowserSpyReportSnapshot(
                BrowserReportStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="Открой раздел системных сообщений, чтобы #TabAdministrativeBox был загружен",
                )
            )

        try:
            reports = parse_rendered_spy_reports(str(raw.get("html") or ""))
        except Exception as exc:
            return BrowserSpyReportSnapshot(
                BrowserReportStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail=f"Не удалось разобрать разведданные: {exc}",
                )
            )
        return BrowserSpyReportSnapshot(
            BrowserReportStatus(
                True,
                endpoint=self.endpoint,
                page_url=page_url,
                detail=f"Attach-only reports · {page_url}",
            ),
            reports,
        )
