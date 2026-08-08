from __future__ import annotations

from v2.application.report_source import BrowserReportStatus, BrowserSpyReportSnapshot
from v2.infrastructure.cdp_read_backend import CdpReadError, ReadOnlyCdpBackend, extract_coord
from v2.infrastructure.spy_report_parser import parse_rendered_spy_reports


class ReadOnlyAccountCdpBackend(ReadOnlyCdpBackend):
    """Extend attach-only fleet reads with account and rendered report facts.

    The reader only inspects DOM from pages already open in the connected browser.
    It never follows links, switches planets, creates tabs, loads message tabs or
    navigates to another game page.
    """

    async def _read_owned_planets(self) -> tuple[str, ...]:
        page = await self._existing_fleets_page()
        try:
            values = await page.evaluate(
                r"""() => Array.from(document.querySelectorAll('#planetsListHolder a'))
                    .map(a => (a.textContent || '').trim())"""
            )
        except Exception as exc:
            raise CdpReadError("Не удалось прочитать список собственных планет") from exc
        coords = {extract_coord(str(value)) for value in values}
        return tuple(sorted(coord for coord in coords if coord.count(":") == 2))

    def owned_planets(self) -> tuple[str, ...]:
        try:
            snapshot = self._snapshot()
        except CdpReadError:
            return ()
        if snapshot.captcha_present:
            return ()
        try:
            return tuple(self._submit(self._read_owned_planets()))
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
