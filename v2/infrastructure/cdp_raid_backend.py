from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Coroutine

from playwright.async_api import Browser, Page, Playwright, async_playwright

from v2.application.raid_actions import (
    RaidActionError,
    RaidCommand,
    RaidDispatchResult,
    RaidPreparation,
)


class V2RaidCdpBackend:
    """Attach to an already-open fleets.php page for guarded raid preparation/dispatch.

    The adapter never launches a browser, creates a page, or navigates. Dispatch is
    one-shot: after the SendFleet request is accepted, V2 verifies a new attack row
    and never retries an ambiguous send automatically.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        game_host: str = "game.ares.nemexia.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.game_host = game_host
        self.timeout_seconds = max(5.0, float(timeout_seconds))
        self._thread = threading.Thread(
            target=self._thread_main,
            daemon=True,
            name="nemexia-v2-cdp-raid",
        )
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._closed = False
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def _submit(self, coroutine: Coroutine[Any, Any, Any], *, timeout: float | None = None) -> Any:
        if self._closed or self._loop is None:
            raise RaidActionError("V2 raid CDP backend is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout or self.timeout_seconds)
        except Exception as exc:
            future.cancel()
            if isinstance(exc, RaidActionError):
                raise
            raise RaidActionError(str(exc) or exc.__class__.__name__) from exc

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.endpoint,
                timeout=int(self.timeout_seconds * 1000),
            )
        except Exception as exc:
            self._browser = None
            raise RaidActionError(f"CDP недоступен: {self.endpoint}") from exc
        return self._browser

    async def _existing_fleets_page(self) -> Page:
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        page = next(
            (
                item
                for item in pages
                if self.game_host in item.url and "fleets.php" in item.url
            ),
            None,
        )
        if page is None:
            raise RaidActionError("Открой fleets.php в уже подключённом браузере")
        return page

    async def _captcha_present(self, page: Page) -> bool:
        return bool(
            await page.evaluate(
                r"""() => {
                    const text=(document.body?.innerText||'').replace(/\s+/g,' ').toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    return recaptcha || botLock || [
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ].some(value => text.includes(value));
                }"""
            )
        )

    async def _assert_ready(self, page: Page, command: RaidCommand) -> None:
        if await self._captcha_present(page):
            raise RaidActionError(
                "CAPTCHA обнаружена. V2 остановил действие до ручного подтверждения."
            )
        current = str(
            await page.evaluate(
                """() => {
                    const v=id => document.querySelector(id)?.value || '';
                    return [v('#my_c1'),v('#my_c2'),v('#my_c3')].join(':');
                }"""
            )
            or ""
        )
        if current and current != command.home:
            raise RaidActionError(
                f"Сейчас выбрана планета {current}, а для рейда требуется {command.home}. "
                "Переключи планету вручную."
            )

    async def _prepare(self, command: RaidCommand) -> RaidPreparation:
        page = await self._existing_fleets_page()
        await self._assert_ready(page, command)
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        try:
            await page.locator("#TabChooseShips").wait_for(state="visible", timeout=7_000)
            await page.locator("#ship_1_2").wait_for(state="attached", timeout=7_000)
        except Exception as exc:
            raise RaidActionError("Поле мегатранспортировщика не найдено") from exc

        available = int(await page.locator("#ship_1_2_max").get_attribute("value") or 0)
        if available < command.ship_count:
            raise RaidActionError(
                f"Доступно только {available} мегатранспортировщиков, требуется {command.ship_count}."
            )

        await page.evaluate(
            """() => document.querySelectorAll('input.ships').forEach(el => {
                el.value='0'; el.dispatchEvent(new Event('change', {bubbles:true}));
            })"""
        )
        await page.locator("select#mission").select_option("3")
        await page.evaluate("() => { if (typeof selectMissionImg === 'function') selectMissionImg(3); }")
        await page.locator("#ship_1_2").fill(str(command.ship_count))
        await page.locator("#ship_1_2").dispatch_event("change")
        await page.evaluate("() => shipsCheck()")
        try:
            await page.locator("#TabSendFleets").wait_for(state="visible", timeout=12_000)
        except Exception as exc:
            raise RaidActionError("Игра не перешла к вводу координат") from exc

        g, s, p = command.target.split(":")
        for selector, value in (("#target_c1", g), ("#target_c2", s), ("#target_c3", p)):
            locator = page.locator(selector)
            await locator.fill(value)
            await locator.dispatch_event("change")

        timing = await page.evaluate(
            """() => {
                if (typeof FlyCheck !== 'function') throw new Error('FlyCheck missing');
                FlyCheck();
                const number=value => {
                    const n=String(value||'').replace(/[^0-9]/g,'');
                    return n ? Number(n) : null;
                };
                return {
                    one:Number(window.seconds||0),
                    round:Number(window.seconds2||0),
                    gas:number(document.querySelector('#missionGasNeeded')?.textContent)
                };
            }"""
        )
        one = int(timing.get("one") or 0)
        round_trip = int(timing.get("round") or 0)
        if one <= 0 or round_trip <= 0:
            raise RaidActionError(f"Игра не рассчитала время до {command.target}")
        await self._assert_ready(page, command)
        return RaidPreparation(
            source=command.home,
            target=command.target,
            player=command.player,
            ship_count=command.ship_count,
            one_way_seconds=one,
            round_trip_seconds=round_trip,
            gas_needed=timing.get("gas"),
        )

    @staticmethod
    def _extract_coord(value: object) -> str:
        match = re.search(r"(\d+)\s*:\s*(\d+)\s*:\s*(\d+)", str(value or ""))
        return ":".join(match.groups()) if match else str(value or "").replace(" ", "")

    async def _read_flight_rows(self, page: Page) -> list[dict[str, str | None]]:
        return await page.evaluate(
            r"""() => Array.from(document.querySelectorAll('#fleetHandler tbody tr')).map(row => {
                const cells=Array.from(row.children).filter(el=>el.tagName==='TD');
                const details=row.querySelector('.fleetType a');
                const onclick=details?.getAttribute('onclick')||'';
                const match=onclick.match(/fleetDetails\((\d+)\)/);
                return {
                    id:match?match[1]:null,
                    source:cells[0]?.textContent?.trim()||'',
                    target:cells[1]?.textContent?.trim()||'',
                    mission:details?.textContent?.trim()||cells[4]?.textContent?.trim()||''
                };
            })"""
        )

    async def _dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        preparation = await self._prepare(command)
        page = await self._existing_fleets_page()
        await self._assert_ready(page, command)
        before_rows = await self._read_flight_rows(page)
        before_ids = {str(row["id"]) for row in before_rows if row.get("id")}

        button = page.locator("#SendFleetButton")
        if await button.is_disabled():
            raise RaidActionError(
                "Игра не разрешает отправку. Проверь корабли, газ, координаты и свободные слоты."
            )

        try:
            async with page.expect_response(
                lambda response: (
                    "ajax_fleets.php" in response.url
                    and response.request.method == "POST"
                    and "type=SendFleet" in (response.request.post_data or "")
                ),
                timeout=15_000,
            ) as response_info:
                await button.click()
            response = await response_info.value
            response_text = await response.text()
        except Exception as exc:
            if await self._captcha_present(page):
                raise RaidActionError(
                    "CAPTCHA появилась при отправке. Повтор автоматически запрещён."
                ) from exc
            raise RaidActionError(
                "Не получен однозначный ответ на отправку. Не повторяй рейд до проверки экрана «Активные»."
            ) from exc

        try:
            payload = json.loads(response_text)
            pass_value = str(payload.get("pass"))
            server_info = str(payload.get("info") or "")
        except Exception as exc:
            raise RaidActionError(
                "Ответ SendFleet не распознан. Запрос мог быть принят; автоматический повтор запрещён."
            ) from exc
        if pass_value == "0":
            raise RaidActionError(server_info or "Игра отклонила отправку флота")
        if pass_value not in {"1", "True", "true"}:
            raise RaidActionError(
                "Ответ SendFleet неоднозначен. Запрос мог быть принят; автоматический повтор запрещён."
            )

        sent_at = datetime.now().astimezone()
        try:
            await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
        except Exception:
            pass

        fleet_id: str | None = None
        verified = False
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.45)
            if await self._captcha_present(page):
                break
            rows = await self._read_flight_rows(page)
            candidates = [
                row
                for row in rows
                if row.get("id")
                and str(row["id"]) not in before_ids
                and self._extract_coord(row.get("target")) == command.target
                and str(row.get("mission") or "").strip().casefold() == "атака"
            ]
            if candidates:
                fleet_id = str(candidates[0]["id"])
                verified = True
                break

        return RaidDispatchResult(
            source=preparation.source,
            target=preparation.target,
            player=preparation.player,
            ship_count=preparation.ship_count,
            sent_at=sent_at.isoformat(),
            arrival_at=(sent_at + timedelta(seconds=preparation.one_way_seconds)).isoformat(),
            return_at=(sent_at + timedelta(seconds=preparation.round_trip_seconds)).isoformat(),
            fleet_id=fleet_id,
            verified=verified,
            server_info=server_info,
        )

    def prepare(self, command: RaidCommand) -> RaidPreparation:
        return self._submit(self._prepare(command))

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        return self._submit(self._dispatch(command), timeout=self.timeout_seconds + 20.0)

    async def _stop_playwright(self) -> None:
        # This backend attaches to a browser owned by the user. Never Browser.close().
        self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._submit(self._stop_playwright())
        except Exception:
            pass
        self._closed = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
