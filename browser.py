from __future__ import annotations

import asyncio
import json
import hashlib
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Coroutine

from playwright.async_api import Browser, Page, Playwright, async_playwright

from asteroids import movement_margin_seconds, parse_asteroid_tooltip, predict_coordinate
from config import FLEETS_URL, GALAXY_URL, GAME_HOST, MESSAGES_URL, PROFILE_DIR, SCREENSHOT_DIR
from models import AsteroidObservation, AsteroidPlan, CombatReport, Flight, SpyReport, Target, utc_now
from reports import parse_battle_reports_html, parse_spy_reports_html


class BrowserAutomationError(RuntimeError):
    pass


class CaptchaRequiredError(BrowserAutomationError):
    """Nemexia requires an explicit human confirmation. Never bypass it."""


class UnverifiedSendError(BrowserAutomationError):
    """The server accepted a send request, but the flight row was not confirmed."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


ASTEROID_CANDIDATE_RESERVE = 5
MAX_ASTEROID_CANDIDATES = 200


def parse_hms(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", value)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def extract_coord(value: str | None) -> str:
    match = re.search(r"(\d+)\s*:\s*(\d+)\s*:\s*(\d+)", value or "")
    return ":".join(match.groups()) if match else (value or "").replace(" ", "")


def find_yandex_browser() -> Path | None:
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    if local:
        candidates.extend([
            Path(local) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe",
            Path(local) / "Yandex" / "YandexBrowserBeta" / "Application" / "browser.exe",
        ])
    if program_files:
        candidates.append(Path(program_files) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe")
    return next((path for path in candidates if path.exists()), None)


def cdp_is_available(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def launch_yandex(port: int) -> subprocess.Popen[Any]:
    executable = find_yandex_browser()
    if executable is None:
        raise BrowserAutomationError("Яндекс Браузер не найден в стандартных папках")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        FLEETS_URL,
    ]
    try:
        return subprocess.Popen(command, cwd=PROFILE_DIR)
    except OSError as exc:
        raise BrowserAutomationError(f"Не удалось запустить Яндекс Браузер: {exc}") from exc


class BrowserWorker:
    """All Playwright calls run on one dedicated asyncio thread."""

    def __init__(self) -> None:
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="nemexia-browser")
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._endpoint: str | None = None
        self._thread.start()
        self._ready.wait(timeout=5)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    def submit(self, coroutine: Coroutine[Any, Any, Any]):
        if self._loop is None:
            raise RuntimeError("Browser worker is not ready")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    async def shutdown(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None

    async def connect(self, endpoint: str) -> dict[str, Any]:
        if self._browser and self._endpoint == endpoint:
            try:
                page = await self._select_nemexia_page()
                return {"url": page.url, "pages": self._page_count()}
            except Exception:
                self._browser = None
                self._page = None
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint, timeout=12_000)
        except Exception as exc:
            self._browser = None
            raise BrowserAutomationError(
                "Не удалось подключиться к браузеру. Запусти его из приложения и повтори подключение."
            ) from exc
        self._endpoint = endpoint
        page = await self._select_nemexia_page(create_if_missing=True)
        return {"url": page.url, "pages": self._page_count()}

    async def ping(self) -> bool:
        try:
            page = await self._select_nemexia_page()
            return not page.is_closed()
        except Exception:
            return False

    def _page_count(self) -> int:
        if not self._browser:
            return 0
        return sum(len(context.pages) for context in self._browser.contexts)

    async def _select_nemexia_page(self, create_if_missing: bool = False) -> Page:
        if not self._browser:
            raise BrowserAutomationError("Браузер не подключён")
        pages = [page for context in self._browser.contexts for page in context.pages if not page.is_closed()]
        game_pages = [page for page in pages if GAME_HOST in page.url]
        page = next((item for item in game_pages if "fleets.php" in item.url), None)
        page = page or (game_pages[0] if game_pages else None)
        if page is None and create_if_missing:
            if not self._browser.contexts:
                raise BrowserAutomationError("В браузере нет доступного контекста")
            page = await self._browser.contexts[0].new_page()
            await page.goto(FLEETS_URL, wait_until="domcontentloaded", timeout=30_000)
        if page is None:
            raise BrowserAutomationError("Вкладка Nemexia не найдена")
        self._page = page
        return page

    async def _diagnostic(self, label: str) -> str | None:
        page = self._page
        if page is None or page.is_closed():
            return None
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{label}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return None

    async def _captcha_details(self, page: Page) -> dict[str, Any]:
        try:
            return await page.evaluate(
                r"""() => {
                    const text=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    const phrases=[
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ];
                    const phrase=phrases.find(value => text.toLowerCase().includes(value)) || '';
                    return {present: recaptcha || botLock || !!phrase, recaptcha, botLock, phrase, url: location.href};
                }"""
            )
        except Exception:
            return {"present": False}

    async def _assert_no_captcha(self, page: Page, label: str = "captcha") -> None:
        details = await self._captcha_details(page)
        if not details.get("present"):
            return
        screenshot = await self._diagnostic(label)
        suffix = f" Скриншот: {screenshot}" if screenshot else ""
        raise CaptchaRequiredError(
            "Nemexia запросила подтверждение человека. Автоматические действия остановлены. "
            "Пройди проверку вручную в браузере и запусти цикл снова." + suffix
        )

    async def captcha_present(self) -> bool:
        try:
            page = await self._select_nemexia_page()
            return bool((await self._captcha_details(page)).get("present"))
        except Exception:
            return False

    async def _server_now(self, page: Page) -> datetime:
        values = await page.evaluate(
            r"""() => {
                const d=(window.currentTime instanceof Date && !Number.isNaN(window.currentTime.getTime()))
                    ? window.currentTime : new Date();
                return [d.getFullYear(), d.getMonth()+1, d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds()];
            }"""
        )
        return datetime(*(int(value) for value in values))

    async def _ensure_fleets_page(self) -> Page:
        page = await self._select_nemexia_page(create_if_missing=True)
        if GAME_HOST not in page.url or "fleets.php" not in page.url:
            await page.goto(FLEETS_URL, wait_until="domcontentloaded", timeout=30_000)
        await self._assert_no_captcha(page, "captcha_fleets")
        try:
            await page.locator("#mainFrame").wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            await self._diagnostic("fleets_not_open")
            raise BrowserAutomationError(
                "Страница полётов не открылась. Проверь авторизацию в отдельном профиле браузера."
            ) from exc
        await page.bring_to_front()
        return page

    async def _current_planet_coord(self, page: Page) -> str:
        return await page.evaluate(
            r"""() => {
                const hidden=['#my_c1','#my_c2','#my_c3'].map(id => document.querySelector(id)?.value || '');
                if(hidden.every(Boolean)) return hidden.join(':');
                const text=document.querySelector('#planetSwitch .trigger big')?.textContent || '';
                const m=text.match(/\[(\d+)\s*:\s*(\d+)\s*:\s*(\d+)\]/);
                return m ? [m[1],m[2],m[3]].join(':') : '';
            }"""
        )

    async def _select_planet(self, page: Page, home: tuple[int, int, int]) -> str:
        await self._assert_no_captcha(page, "captcha_planet_switch")
        expected = ":".join(map(str, home))
        current = await self._current_planet_coord(page)
        if current == expected:
            return expected
        link = await page.evaluate(
            r"""coord => {
                const links=Array.from(document.querySelectorAll('#planetsListHolder a'));
                const item=links.find(a => (a.textContent||'').replace(/\s+/g,'').includes('['+coord+']'));
                return item?.href || '';
            }""",
            expected,
        )
        if not link:
            raise BrowserAutomationError(f"Планета {expected} не найдена в списке твоих планет")
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=30_000)
            await page.locator("#planetSwitch").wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            await self._diagnostic("planet_switch_failed")
            raise BrowserAutomationError(f"Не удалось переключиться на планету {expected}") from exc
        await self._assert_no_captcha(page, "captcha_after_planet_switch")
        current = await self._current_planet_coord(page)
        if current != expected:
            raise BrowserAutomationError(f"Игра оставила планету {current or 'неизвестно'}, ожидалась {expected}")
        return expected

    async def _ensure_galaxy_page(
        self,
        home: tuple[int, int, int],
        galaxy: int,
        solar: int,
    ) -> Page:
        page = await self._select_nemexia_page(create_if_missing=True)
        await self._select_planet(page, home)
        url = f"{GALAXY_URL}?galaxy={int(galaxy)}&solar={int(solar)}"
        if "galaxy.php" not in page.url:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.locator("#galaxyHolder").wait_for(state="attached", timeout=15_000)
            await page.locator("#c1").wait_for(state="attached", timeout=15_000)
            await page.locator("#c2").wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            await self._diagnostic("galaxy_not_open")
            raise BrowserAutomationError("Страница галактики не открылась") from exc
        await self._assert_no_captcha(page, "captcha_galaxy")
        await page.bring_to_front()
        await self._load_galaxy_system(page, galaxy, solar)
        return page

    async def _load_galaxy_system(self, page: Page, galaxy: int, solar: int) -> None:
        await self._assert_no_captcha(page, "captcha_before_galaxy_load")
        if solar < 1 or solar > 40:
            raise BrowserAutomationError("Солнечная система должна быть в диапазоне 1–40")
        before = await page.locator("#galaxyHolder").inner_html()
        try:
            async with page.expect_response(
                lambda response: "ajax_galaxy.php" in response.url and response.request.method == "POST",
                timeout=20_000,
            ):
                await page.evaluate(
                    """args => {
                        const [g,s]=args;
                        document.querySelector('#c1').value=String(g);
                        document.querySelector('#c2').value=String(s);
                        if(typeof refreshGalaxy!=='function') throw new Error('refreshGalaxy missing');
                        refreshGalaxy();
                    }""",
                    [int(galaxy), int(solar)],
                )
        except Exception as exc:
            await self._diagnostic(f"galaxy_{galaxy}_{solar}_load_failed")
            raise BrowserAutomationError(f"Не загрузилась система {galaxy}:{solar}") from exc
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
                arg=[int(galaxy), int(solar), before],
                timeout=20_000,
            )
        except Exception:
            # A refresh can return byte-identical HTML. In that case the response and
            # hidden loader are enough to accept the selected coordinates.
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
                arg=[int(galaxy), int(solar)],
                timeout=8_000,
            )
        await self._assert_no_captcha(page, "captcha_after_galaxy_load")

    async def _read_asteroid_links(self, page: Page) -> list[tuple[int, int, int]]:
        raw = await page.evaluate(
            r"""() => Array.from(document.querySelectorAll('#galaxyHolder a')).map(a => {
                const img=a.querySelector('img[src*="asteroid"]');
                if(!img) return null;
                const href=a.getAttribute('href')||'';
                const hover=a.getAttribute('onmouseover')||'';
                let m=href.match(/[?&]c1=(\d+).*?[?&]c2=(\d+).*?[?&]c3=(\d+)/);
                if(!m) m=hover.match(/squareInfo\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)/);
                return m ? [Number(m[1]),Number(m[2]),Number(m[3])] : null;
            }).filter(Boolean)"""
        )
        return [tuple(int(value) for value in item) for item in raw]

    async def _fetch_asteroid_info(self, page: Page, g: int, s: int, p: int) -> str:
        await self._assert_no_captcha(page, "captcha_asteroid_info")
        try:
            result = await page.evaluate(
                """args => {
                    const [g,s,p]=args;
                    return fetch('ajax_info.php', {
                        method:'POST',
                        credentials:'same-origin',
                        headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                        body:new URLSearchParams({type:'squareInfo',c1:String(g),c2:String(s),c3:String(p)}).toString()
                    }).then(response => response.text());
                }""",
                [int(g), int(s), int(p)],
            )
        except Exception as exc:
            raise BrowserAutomationError(f"Не получена информация об астероиде {g}:{s}:{p}") from exc
        if re.search(r"are you human|защита от автоматических действий|g-recaptcha", result or "", re.I):
            await self._diagnostic("captcha_asteroid_response")
            raise CaptchaRequiredError("Nemexia запросила подтверждение человека во время сканирования")
        return str(result or "")

    async def scan_asteroids(
        self,
        *,
        home: tuple[int, int, int],
        galaxy: int = 3,
        start_system: int = 39,
        end_system: int = 1,
        limit: int = 15,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[AsteroidObservation]:
        if start_system < end_system:
            raise BrowserAutomationError("Сканирование астероидов поддерживает движение только вниз")
        page = await self._ensure_galaxy_page(home, galaxy, start_system)
        observations: list[AsteroidObservation] = []
        seen: set[str] = set()
        for solar in range(int(start_system), int(end_system) - 1, -1):
            if cancelled and cancelled():
                break
            if progress:
                progress(f"Сканирование системы {galaxy}:{solar} · найдено {len(observations)}/{limit}")
            await self._load_galaxy_system(page, galaxy, solar)
            server_now = await self._server_now(page)
            links = await self._read_asteroid_links(page)
            for g, s, p in links:
                coord = f"{g}:{s}:{p}"
                if coord in seen:
                    continue
                seen.add(coord)
                try:
                    tooltip = await self._fetch_asteroid_info(page, g, s, p)
                    observation = parse_asteroid_tooltip(tooltip, g, s, p, server_now)
                except CaptchaRequiredError:
                    raise
                except Exception:
                    continue
                observations.append(observation)
                if progress:
                    progress(f"Найден астероид {coord} · {len(observations)}/{limit}")
                if len(observations) >= max(1, int(limit)):
                    return observations
        return observations

    async def _scan_asteroid_batch(
        self,
        *,
        home: tuple[int, int, int],
        galaxy: int,
        start_system: int,
        end_system: int,
        limit: int,
        cancelled: Callable[[], bool] | None,
        progress: Callable[[str], None] | None,
    ) -> tuple[list[AsteroidObservation], int, bool]:
        """Scan one candidate batch and advance the system cursor strictly down."""
        observations = await self.scan_asteroids(
            home=home,
            galaxy=galaxy,
            start_system=start_system,
            end_system=end_system,
            limit=limit,
            cancelled=cancelled,
            progress=progress,
        )
        if not observations:
            return observations, int(end_system) - 1, True
        next_system = min(observation.s for observation in observations) - 1
        return observations, next_system, next_system < int(end_system)

    @staticmethod
    def asteroid_candidate_limit(requested: int, *, reserve: int = ASTEROID_CANDIDATE_RESERVE) -> int:
        """Return the bounded candidate count for one dynamic scan pass."""
        return min(MAX_ASTEROID_CANDIDATES, max(1, int(requested)) + max(0, int(reserve)))

    async def _visible_error(self, page: Page) -> str:
        messages: list[str] = []
        for selector in [".ui-dialog:visible", ".ui-pnotify:visible", ".alert:visible", "#dialog-message:visible"]:
            try:
                count = await page.locator(selector).count()
                for index in range(min(count, 3)):
                    text = (await page.locator(selector).nth(index).inner_text()).strip()
                    if text:
                        messages.append(" ".join(text.split()))
            except Exception:
                continue
        return " | ".join(dict.fromkeys(messages))

    async def _verify_home(self, page: Page, home: tuple[int, int, int]) -> str:
        current = await page.evaluate(
            """() => {
              const v = id => document.querySelector(id)?.value || '';
              return [v('#my_c1'), v('#my_c2'), v('#my_c3')].join(':');
            }"""
        )
        expected = ":".join(map(str, home))
        if current and current != expected:
            raise BrowserAutomationError(
                f"Сейчас выбрана планета {current}, а должна быть {expected}."
            )
        return current or expected

    async def _prepare_fleet(self, page: Page, ship_count: int, home: tuple[int, int, int]) -> str:
        if ship_count <= 0:
            raise BrowserAutomationError("Количество кораблей должно быть больше нуля")
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        try:
            await page.locator("#TabChooseShips").wait_for(state="visible", timeout=7_000)
            await page.locator("#ship_1_2").wait_for(state="attached", timeout=7_000)
        except Exception as exc:
            await self._diagnostic("ship_field_missing")
            raise BrowserAutomationError(
                "Поле мегатранспортировщика не найдено. Проверь исходную планету и наличие кораблей."
            ) from exc
        max_value_raw = await page.locator("#ship_1_2_max").get_attribute("value")
        available = int(max_value_raw or 0)
        if available < ship_count:
            raise BrowserAutomationError(
                f"Доступно только {available} мегатранспортировщиков, требуется {ship_count}."
            )
        await page.evaluate(
            """() => document.querySelectorAll('input.ships').forEach(el => {
              el.value = '0'; el.dispatchEvent(new Event('change', {bubbles:true}));
            })"""
        )
        await page.locator("select#mission").select_option("3")
        await page.evaluate("() => { if (typeof selectMissionImg === 'function') selectMissionImg(3); }")
        await page.locator("#ship_1_2").fill(str(ship_count))
        await page.locator("#ship_1_2").dispatch_event("change")
        await page.evaluate("() => shipsCheck()")
        try:
            await page.locator("#TabSendFleets").wait_for(state="visible", timeout=12_000)
        except Exception as exc:
            error = await self._visible_error(page)
            await self._diagnostic("ships_check_failed")
            raise BrowserAutomationError(
                f"Игра не перешла к координатам.{(' Ошибка игры: ' + error) if error else ''}"
            ) from exc
        return await self._verify_home(page, home)

    async def _prepare_recycler_fleet(self, page: Page, ship_count: int, home: tuple[int, int, int]) -> str:
        if ship_count <= 0:
            raise BrowserAutomationError("Количество переработчиков должно быть больше нуля")
        await self._assert_no_captcha(page, "captcha_prepare_recyclers")
        await self._select_planet(page, home)
        if "fleets.php" not in page.url:
            await page.goto(FLEETS_URL, wait_until="domcontentloaded", timeout=30_000)
        await self._assert_no_captcha(page, "captcha_recycler_fleets")
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        try:
            await page.locator("#TabChooseShips").wait_for(state="visible", timeout=7_000)
            await page.locator("#ship_1_11").wait_for(state="attached", timeout=7_000)
        except Exception as exc:
            await self._diagnostic("recycler_field_missing")
            raise BrowserAutomationError(
                "Поле переработчика не найдено. Проверь планету Питер и наличие кораблей."
            ) from exc
        max_value_raw = await page.locator("#ship_1_11_max").get_attribute("value")
        available = int(max_value_raw or 0)
        if available < ship_count:
            raise BrowserAutomationError(f"Доступно только {available} переработчиков, требуется {ship_count}.")
        await page.evaluate(
            """() => document.querySelectorAll('input.ships').forEach(el => {
              el.value = '0'; el.dispatchEvent(new Event('change', {bubbles:true}));
            })"""
        )
        await page.locator("select#mission").select_option("8")
        await page.evaluate("() => { if (typeof selectMissionImg === 'function') selectMissionImg(8); }")
        await page.locator("#ship_1_11").fill(str(ship_count))
        await page.locator("#ship_1_11").dispatch_event("change")
        await page.evaluate("() => shipsCheck()")
        try:
            await page.locator("#TabSendFleets").wait_for(state="visible", timeout=12_000)
        except Exception as exc:
            error = await self._visible_error(page)
            await self._diagnostic("recyclers_check_failed")
            raise BrowserAutomationError(
                f"Игра не перешла к координатам для переработчиков.{(' Ошибка игры: ' + error) if error else ''}"
            ) from exc
        await self._assert_no_captcha(page, "captcha_after_recycler_select")
        return await self._verify_home(page, home)

    async def available_recyclers(self, home: tuple[int, int, int]) -> int:
        page = await self._ensure_fleets_page()
        await self._select_planet(page, home)
        if "fleets.php" not in page.url:
            await page.goto(FLEETS_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        await page.locator("#ship_1_11_max").wait_for(state="attached", timeout=10_000)
        return int(await page.locator("#ship_1_11_max").get_attribute("value") or 0)

    async def _set_target(self, page: Page, target: Target) -> dict[str, Any]:
        for selector, value in (("#target_c1", target.g), ("#target_c2", target.s), ("#target_c3", target.p)):
            locator = page.locator(selector)
            await locator.fill(str(value))
            await locator.dispatch_event("change")
        result = await page.evaluate(
            """() => {
              FlyCheck();
              const number = value => { const n=String(value||'').replace(/[^0-9]/g,''); return n?Number(n):null; };
              return {
                one:Number(window.seconds||0), round:Number(window.seconds2||0),
                oneText:document.querySelector('#missionOneWay')?.textContent?.trim()||'',
                roundText:document.querySelector('#missionTwoWay')?.textContent?.trim()||'',
                arrivalClock:document.querySelector('#missionOneWayTime')?.textContent?.trim()||'',
                returnClock:document.querySelector('#missionTwoWayTime')?.textContent?.trim()||'',
                gas:number(document.querySelector('#missionGasNeeded')?.textContent)
              };
            }"""
        )
        if not result.get("one") or not result.get("round"):
            await self._diagnostic("time_not_calculated")
            raise BrowserAutomationError(f"Игра не рассчитала время до {target.coord}")
        return result

    async def _set_target_coords(self, page: Page, g: int, s: int, p: int) -> dict[str, Any]:
        coord = f"{int(g)}:{int(s)}:{int(p)}"
        for selector, value in (("#target_c1", g), ("#target_c2", s), ("#target_c3", p)):
            locator = page.locator(selector)
            await locator.fill(str(int(value)))
            await locator.dispatch_event("change")
        result = await page.evaluate(
            """() => {
              FlyCheck();
              const number = value => { const n=String(value||'').replace(/[^0-9]/g,''); return n?Number(n):null; };
              return {
                one:Number(window.seconds||0), round:Number(window.seconds2||0),
                oneText:document.querySelector('#missionOneWay')?.textContent?.trim()||'',
                roundText:document.querySelector('#missionTwoWay')?.textContent?.trim()||'',
                arrivalClock:document.querySelector('#missionOneWayTime')?.textContent?.trim()||'',
                returnClock:document.querySelector('#missionTwoWayTime')?.textContent?.trim()||'',
                gas:number(document.querySelector('#missionGasNeeded')?.textContent)
              };
            }"""
        )
        if not result.get("one") or not result.get("round"):
            await self._diagnostic("asteroid_time_not_calculated")
            raise BrowserAutomationError(f"Игра не рассчитала время до {coord}")
        return result

    async def prepare_raid(self, target: Target, ship_count: int, home: tuple[int, int, int]) -> dict[str, Any]:
        page = await self._ensure_fleets_page()
        source = await self._prepare_fleet(page, ship_count, home)
        timing = await self._set_target(page, target)
        return {"source": source, "target": target.coord, **timing}

    async def calculate_times(self, targets: list[Target], ship_count: int, home: tuple[int, int, int]) -> list[dict[str, Any]]:
        page = await self._ensure_fleets_page()
        source = await self._prepare_fleet(page, ship_count, home)
        output: list[dict[str, Any]] = []
        for target in targets:
            values = await self._set_target(page, target)
            output.append({
                "coord": target.coord, "source": source, "one": int(values["one"]),
                "round": int(values["round"]), "gas": values.get("gas"),
            })
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        return output

    async def _resolve_asteroid_plan(
        self,
        page: Page,
        observation: AsteroidObservation,
        *,
        safety_seconds: int,
        max_iterations: int = 8,
    ) -> AsteroidPlan:
        server_now = await self._server_now(page)
        try:
            candidate, _ = predict_coordinate(observation, server_now, safety_seconds=0, max_system=40)
        except ValueError as exc:
            raise BrowserAutomationError(str(exc)) from exc
        for _ in range(max_iterations):
            timing = await self._set_target_coords(page, *candidate)
            server_now = await self._server_now(page)
            arrival_server = server_now + timedelta(seconds=int(timing["one"]))
            try:
                predicted, shifts = predict_coordinate(
                    observation,
                    arrival_server,
                    safety_seconds=0,
                    max_system=40,
                )
            except ValueError as exc:
                raise BrowserAutomationError(str(exc)) from exc
            if predicted == candidate:
                margin = movement_margin_seconds(
                    observation.next_move_server, observation.period_seconds, arrival_server
                )
                if safety_seconds > 0 and margin < safety_seconds:
                    raise BrowserAutomationError(
                        f"Прибытие к {observation.coord} слишком близко к перемещению астероида "
                        f"({margin:.1f} сек. при запасе {safety_seconds} сек.)"
                    )
                return AsteroidPlan(
                    observation=observation,
                    target_g=predicted[0], target_s=predicted[1], target_p=predicted[2],
                    shifts=shifts,
                    one_way_seconds=int(timing["one"]),
                    round_trip_seconds=int(timing["round"]),
                    arrival_server_at=arrival_server,
                    return_server_at=server_now + timedelta(seconds=int(timing["round"])),
                    gas_needed=timing.get("gas"),
                )
            candidate = predicted
        raise BrowserAutomationError(f"Не стабилизировался расчёт цели для астероида {observation.coord}")

    async def plan_asteroid_wave(
        self,
        observations: list[AsteroidObservation],
        *,
        recycler_count: int,
        home: tuple[int, int, int],
        safety_seconds: int = 10,
        progress: Callable[[str], None] | None = None,
    ) -> list[AsteroidPlan]:
        page = await self._ensure_fleets_page()
        await self._select_planet(page, home)
        await self._prepare_recycler_fleet(page, recycler_count, home)
        plans: list[AsteroidPlan] = []
        for index, observation in enumerate(observations, start=1):
            await self._assert_no_captcha(page, "captcha_asteroid_plan")
            if progress:
                progress(f"Расчёт астероида {index}/{len(observations)} · {observation.coord}")
            plans.append(await self._resolve_asteroid_plan(
                page, observation, safety_seconds=max(0, int(safety_seconds))
            ))
        await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
        return plans

    async def _read_flights_from_page(self, page: Page) -> list[dict[str, str | None]]:
        return await page.evaluate(
            r"""() => Array.from(document.querySelectorAll('#fleetHandler tbody tr')).map(row => {
              const cells=Array.from(row.children).filter(el=>el.tagName==='TD');
              const details=row.querySelector('.fleetType a');
              const onclick=details?.getAttribute('onclick')||'';
              const match=onclick.match(/fleetDetails\((\d+)\)/);
              return {
                id:match?match[1]:null,
                source:cells[0]?.textContent?.trim()||'', target:cells[1]?.textContent?.trim()||'',
                arrival:row.querySelector('[id^="arrive1Time-"]')?.textContent?.trim()||'',
                returning:row.querySelector('[id^="arrive2Time-"]')?.textContent?.trim()||'',
                mission:details?.textContent?.trim()||cells[4]?.textContent?.trim()||''
              };
            })"""
        )

    async def sync_flights(self) -> list[Flight]:
        return [flight for flight in await self.sync_all_flights() if flight.mission.strip().lower() == "атака"]

    async def sync_all_flights(self) -> list[Flight]:
        page = await self._ensure_fleets_page()
        try:
            await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
            await asyncio.sleep(0.8)
        except Exception:
            pass
        raw = await self._read_flights_from_page(page)
        now = utc_now().replace(microsecond=0)
        flights: list[Flight] = []
        for row in raw:
            mission = str(row.get("mission") or "")
            arrival_seconds = parse_hms(str(row.get("arrival") or ""))
            return_seconds = parse_hms(str(row.get("returning") or ""))
            if arrival_seconds is None and return_seconds is None:
                continue
            arrival_at = now + timedelta(seconds=arrival_seconds) if arrival_seconds is not None else None
            return_at = now + timedelta(seconds=return_seconds) if return_seconds is not None else None
            sent_at = arrival_at + (arrival_at - return_at) if arrival_at and return_at else None
            flights.append(Flight(
                fleet_id=str(row.get("id")) if row.get("id") else None,
                source=extract_coord(str(row.get("source") or "")), target=extract_coord(str(row.get("target") or "")),
                mission=mission, arrival_at=arrival_at, return_at=return_at, sent_at=sent_at,
            ))
        return flights

    async def sync_asteroid_flights(self) -> list[Flight]:
        return [
            flight for flight in await self.sync_all_flights()
            if flight.mission.strip().lower() == "добыча газа"
        ]

    async def _send_raid_once(self, page: Page, target: Target, ship_count: int, home: tuple[int, int, int]) -> dict[str, Any]:
        source = await self._prepare_fleet(page, ship_count, home)
        timing = await self._set_target(page, target)
        before_rows = await self._read_flights_from_page(page)
        before_ids = {str(item["id"]) for item in before_rows if item.get("id")}
        button = page.locator("#SendFleetButton")
        if await button.is_disabled():
            await button.evaluate("el => el.removeAttribute('disabled')")
        try:
            async with page.expect_response(
                lambda response: (
                    "ajax_fleets.php" in response.url and response.request.method == "POST"
                    and "type=SendFleet" in (response.request.post_data or "")
                ), timeout=15_000,
            ) as response_info:
                await button.click()
            response = await response_info.value
            response_text = await response.text()
        except Exception as exc:
            error = await self._visible_error(page)
            await self._diagnostic("send_no_response")
            raise BrowserAutomationError(
                f"Не получен ответ на отправку.{(' Ошибка игры: ' + error) if error else ''}"
            ) from exc
        pass_value: str | None = None
        info_value = ""
        try:
            payload = json.loads(response_text)
            pass_value = str(payload.get("pass"))
            info_value = str(payload.get("info") or "")
        except Exception:
            pass_match = re.search(r'["\']pass["\']\s*:\s*["\']?(\d+)', response_text)
            info_match = re.search(r'["\']info["\']\s*:\s*["\']([^"\']*)', response_text)
            pass_value = pass_match.group(1) if pass_match else None
            info_value = info_match.group(1) if info_match else ""
        if pass_value == "0":
            await self._diagnostic("send_rejected")
            raise BrowserAutomationError(info_value or "Игра отклонила отправку флота")
        # The game has accepted the request at this point.  Capture the local,
        # offset-aware time before waiting for the table to redraw.
        sent_at = datetime.now().astimezone()
        await asyncio.sleep(0.5)
        try:
            await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
        except Exception:
            pass
        new_row: dict[str, Any] | None = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            await asyncio.sleep(0.45)
            rows = await self._read_flights_from_page(page)
            candidates = [row for row in rows if row.get("id") and str(row["id"]) not in before_ids
                          and str(row.get("target") or "").replace(" ", "") == target.coord
                          and str(row.get("mission") or "").strip().lower() == "атака"]
            if candidates:
                new_row = candidates[0]
                break
        arrival_seconds = int(timing["one"])
        return_seconds = int(timing["round"])
        fleet_id: str | None = None
        if new_row:
            fleet_id = str(new_row.get("id")) if new_row.get("id") else None
        return {
            "fleet_id": fleet_id, "source": source, "target": target.coord, "player": target.player,
            "ship_count": ship_count, "sent_at": sent_at.isoformat(),
            "arrival_at": (sent_at + timedelta(seconds=arrival_seconds)).isoformat(),
            "return_at": (sent_at + timedelta(seconds=return_seconds)).isoformat(),
            "one_way_seconds": arrival_seconds, "round_trip_seconds": return_seconds,
            "gas_needed": timing.get("gas"), "server_info": info_value,
        }

    @staticmethod
    def _is_no_ships_error(message: str) -> bool:
        normalized = " ".join(message.casefold().split())
        return any(phrase in normalized for phrase in (
            "не выбраны корабли",
            "корабли не выбраны",
            "не выбрано ни одного корабля",
        ))

    async def _dismiss_no_ships_popup_and_return(self, page: Page) -> bool:
        """Confirm only Nemexia's known popup, then use the game's own Back action."""
        try:
            await page.locator("#dialogMessage").wait_for(state="visible", timeout=2_500)
        except Exception:
            return False
        dismissed = await page.evaluate(
            """() => {
                const popup = document.querySelector('#dialogMessage');
                if (!popup) return false;
                const controls = Array.from(popup.querySelectorAll('input[type="button"], input[type="submit"], button, a'));
                const ok = controls.find(el => (el.value || el.textContent || '').trim().toLowerCase() === 'ok');
                if (!ok) return false;
                ok.click();
                const back = Array.from(document.querySelectorAll('#TabSendFleets input[type="button"], #TabSendFleets button'))
                    .find(el => (el.value || el.textContent || '').trim().toLowerCase() === 'назад');
                if (back) back.click();
                else if (typeof showTab === 'function') showTab('TabChooseShips');
                else return false;
                return true;
            }"""
        )
        if not dismissed:
            return False
        try:
            await page.locator("#TabChooseShips").wait_for(state="visible", timeout=5_000)
        except Exception:
            return False
        return True

    async def send_raid(self, target: Target, ship_count: int, home: tuple[int, int, int]) -> dict[str, Any]:
        """Send once; retry exactly once only for the known transient ship-selection rejection."""
        page = await self._ensure_fleets_page()
        for attempt in range(2):
            before_rows = await self._read_flights_from_page(page)
            before_ids = {str(row["id"]) for row in before_rows if row.get("id")}
            try:
                return await self._send_raid_once(page, target, ship_count, home)
            except BrowserAutomationError as exc:
                if attempt or not self._is_no_ships_error(str(exc)):
                    raise
                after_rows = await self._read_flights_from_page(page)
                accepted = any(
                    row.get("id") and str(row["id"]) not in before_ids
                    and str(row.get("target") or "").replace(" ", "") == target.coord
                    for row in after_rows
                )
                if accepted:
                    raise BrowserAutomationError(
                        f"Отправка на {target.coord} могла быть принята; повтор не выполнен. Синхронизируй активные рейсы."
                    ) from exc
                if not await self._dismiss_no_ships_popup_and_return(page):
                    raise BrowserAutomationError(
                        f"Ошибка выбора кораблей для {target.coord}; не удалось безопасно подтвердить окно игры. Повтор остановлен."
                    ) from exc
                await self._diagnostic("retry_no_ships")
        raise BrowserAutomationError(f"Повторная отправка на {target.coord} не выполнена")

    async def _send_asteroid_once(
        self,
        page: Page,
        observation: AsteroidObservation,
        recycler_count: int,
        home: tuple[int, int, int],
        safety_seconds: int,
    ) -> dict[str, Any]:
        source = await self._prepare_recycler_fleet(page, recycler_count, home)
        plan = await self._resolve_asteroid_plan(
            page,
            observation,
            safety_seconds=max(0, int(safety_seconds)),
        )
        await self._assert_no_captcha(page, "captcha_before_asteroid_send")
        before_rows = await self._read_flights_from_page(page)
        before_ids = {str(item["id"]) for item in before_rows if item.get("id")}
        button = page.locator("#SendFleetButton")
        if await button.is_disabled():
            error = await self._visible_error(page)
            await self._diagnostic("asteroid_send_disabled")
            raise BrowserAutomationError(
                "Игра не разрешает отправку на астероид."
                + (f" Ошибка игры: {error}" if error else " Проверь газ, корабли и свободные слоты.")
            )
        try:
            async with page.expect_response(
                lambda response: (
                    "ajax_fleets.php" in response.url and response.request.method == "POST"
                    and "type=SendFleet" in (response.request.post_data or "")
                ),
                timeout=15_000,
            ) as response_info:
                await button.click()
            response = await response_info.value
            response_text = await response.text()
        except Exception as exc:
            await self._assert_no_captcha(page, "captcha_asteroid_send_response")
            error = await self._visible_error(page)
            await self._diagnostic("asteroid_send_no_response")
            raise BrowserAutomationError(
                f"Не получен ответ на отправку к астероиду.{(' Ошибка игры: ' + error) if error else ''}"
            ) from exc

        pass_value: str | None = None
        info_value = ""
        try:
            payload = json.loads(response_text)
            pass_value = str(payload.get("pass"))
            info_value = str(payload.get("info") or "")
        except Exception:
            pass_match = re.search(r'["\']pass["\']\s*:\s*["\']?(\d+)', response_text)
            info_match = re.search(r'["\']info["\']\s*:\s*["\']([^"\']*)', response_text)
            pass_value = pass_match.group(1) if pass_match else None
            info_value = info_match.group(1) if info_match else ""
        if pass_value == "0":
            await self._diagnostic("asteroid_send_rejected")
            raise BrowserAutomationError(info_value or "Игра отклонила добычу газа")

        sent_at = datetime.now().astimezone()
        await asyncio.sleep(0.5)
        try:
            await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
        except Exception:
            pass
        new_row: dict[str, Any] | None = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            await asyncio.sleep(0.45)
            await self._assert_no_captcha(page, "captcha_verify_asteroid_send")
            rows = await self._read_flights_from_page(page)
            candidates = [
                row for row in rows
                if row.get("id") and str(row["id"]) not in before_ids
                and str(row.get("target") or "").replace(" ", "") == plan.target_coord
                and str(row.get("mission") or "").strip().lower() == "добыча газа"
            ]
            if candidates:
                new_row = candidates[0]
                break

        result = {
            "fleet_id": str(new_row.get("id")) if new_row and new_row.get("id") else None,
            "source": source,
            "target": plan.target_coord,
            "origin_coord": observation.coord,
            "player": "Астероид",
            "ship_count": recycler_count,
            "mission": "Добыча газа",
            "sent_at": sent_at.isoformat(),
            "arrival_at": (sent_at + timedelta(seconds=plan.one_way_seconds)).isoformat(),
            "return_at": (sent_at + timedelta(seconds=plan.round_trip_seconds)).isoformat(),
            "one_way_seconds": plan.one_way_seconds,
            "round_trip_seconds": plan.round_trip_seconds,
            "gas_needed": plan.gas_needed,
            "shifts": plan.shifts,
            "server_info": info_value,
            "verified": bool(new_row),
        }
        if not new_row:
            await self._diagnostic("asteroid_send_unverified")
            raise UnverifiedSendError(
                "Игра могла принять рейс на астероид, но новая строка полёта не найдена. "
                "Автопродление остановлено, чтобы не создать дубль.",
                result,
            )
        return result

    async def send_asteroid(
        self,
        observation: AsteroidObservation,
        recycler_count: int,
        home: tuple[int, int, int],
        safety_seconds: int = 10,
    ) -> dict[str, Any]:
        page = await self._ensure_fleets_page()
        for attempt in range(2):
            before_rows = await self._read_flights_from_page(page)
            before_ids = {str(row["id"]) for row in before_rows if row.get("id")}
            try:
                return await self._send_asteroid_once(
                    page, observation, recycler_count, home, safety_seconds
                )
            except (CaptchaRequiredError, UnverifiedSendError):
                raise
            except BrowserAutomationError as exc:
                if attempt or not self._is_no_ships_error(str(exc)):
                    raise
                after_rows = await self._read_flights_from_page(page)
                accepted = any(
                    row.get("id") and str(row["id"]) not in before_ids
                    and str(row.get("mission") or "").strip().lower() == "добыча газа"
                    for row in after_rows
                )
                if accepted:
                    raise BrowserAutomationError(
                        "Добыча газа могла быть принята; повтор не выполнен. Синхронизируй полёты."
                    ) from exc
                if not await self._dismiss_no_ships_popup_and_return(page):
                    raise BrowserAutomationError(
                        "Ошибка выбора переработчиков; не удалось безопасно подтвердить окно игры. Повтор остановлен."
                    ) from exc
                await self._diagnostic("retry_no_recyclers")
        raise BrowserAutomationError(f"Повторная отправка к астероиду {observation.coord} не выполнена")

    @staticmethod
    def _is_skippable_asteroid_error(message: str) -> bool:
        normalized = " ".join((message or "").casefold().split())
        return any(phrase in normalized for phrase in (
            "выходит за пределы 40-й солнечной системы",
            "не стабилизировался расчёт цели",
            "некорректные координаты астероида",
            "слишком близко к перемещению астероида",
        ))

    async def run_asteroid_cycle(
        self,
        *,
        home: tuple[int, int, int],
        galaxy: int,
        start_system: int,
        end_system: int,
        recycler_count: int,
        max_flights: int,
        max_slots: int,
        safety_seconds: int,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return await self._run_dynamic_asteroid_cycle(
            home=home,
            galaxy=galaxy,
            start_system=start_system,
            end_system=end_system,
            recycler_count=recycler_count,
            max_flights=max_flights,
            max_slots=max_slots,
            safety_seconds=safety_seconds,
            cancelled=cancelled,
            progress=progress,
        )

        page = await self._select_nemexia_page(create_if_missing=True)
        await self._assert_no_captcha(page, "captcha_asteroid_cycle_start")
        flights = await self.sync_all_flights()
        free_slots = max(0, int(max_slots) - len(flights))
        available = await self.available_recyclers(home)
        requested = min(max(0, int(max_flights)), free_slots, available // max(1, int(recycler_count)))
        if requested <= 0:
            reason = (
                "Нет свободных слотов" if free_slots <= 0
                else f"Недостаточно переработчиков: доступно {available}"
            )
            return {
                "requested": 0, "free_slots": free_slots, "available_recyclers": available,
                "observations": [], "results": [], "error": reason, "error_kind": "capacity",
            }
        # Keep a reserve because a moving asteroid can become invalid only after the
        # exact flight-time calculation (for example when it leaves system 40).
        scan_limit = self.asteroid_candidate_limit(requested)
        observations = await self.scan_asteroids(
            home=home, galaxy=galaxy, start_system=start_system, end_system=end_system,
            limit=scan_limit, cancelled=cancelled, progress=progress,
        )
        if not observations:
            return {
                "requested": requested, "free_slots": free_slots, "available_recyclers": available,
                "observations": [], "results": [], "error": "Астероиды не найдены",
                "error_kind": "no_asteroids",
            }
        results: list[dict[str, Any]] = []
        error: str | None = None
        error_kind: str | None = None
        candidate_index = 0
        for observation in observations:
            if len(results) >= requested:
                break
            candidate_index += 1
            if cancelled and cancelled():
                error = "Операция остановлена пользователем"
                error_kind = "cancelled"
                break
            if progress:
                progress(
                    f"Отправка {len(results) + 1}/{requested} · кандидат {candidate_index}/{len(observations)} "
                    f"· астероид {observation.coord}"
                )
            try:
                results.append(await self.send_asteroid(
                    observation, recycler_count, home, safety_seconds
                ))
            except UnverifiedSendError as exc:
                results.append(exc.result)
                error = str(exc)
                error_kind = "unverified"
                break
            except CaptchaRequiredError as exc:
                error = str(exc)
                error_kind = "captcha"
                break
            except BrowserAutomationError as exc:
                if self._is_skippable_asteroid_error(str(exc)):
                    observation.status = "skipped"
                    observation.error = str(exc)
                    if progress:
                        progress(f"Пропуск {observation.coord}: {exc}")
                    continue
                error = str(exc)
                error_kind = "send"
                break
            except Exception as exc:
                error = str(exc)
                error_kind = "send"
                break
        if not error and len(results) < requested:
            error = f"Удалось отправить только {len(results)} из {requested}: подходящие астероиды закончились"
            error_kind = "not_enough_valid"
        return {
            "requested": requested,
            "free_slots": free_slots,
            "available_recyclers": available,
            "observations": observations,
            "results": results,
            "error": error,
            "error_kind": error_kind,
        }

    async def _run_dynamic_asteroid_cycle(
        self,
        *,
        home: tuple[int, int, int],
        galaxy: int,
        start_system: int,
        end_system: int,
        recycler_count: int,
        max_flights: int,
        max_slots: int,
        safety_seconds: int,
        cancelled: Callable[[], bool] | None,
        progress: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        page = await self._select_nemexia_page(create_if_missing=True)
        await self._assert_no_captcha(page, "captcha_asteroid_cycle_start")
        flights = await self.sync_all_flights()
        free_slots = max(0, int(max_slots) - len(flights))
        available = await self.available_recyclers(home)
        requested = min(max(0, int(max_flights)), free_slots, available // max(1, int(recycler_count)))
        if requested <= 0:
            reason = "Нет свободных слотов" if free_slots <= 0 else f"Недостаточно переработчиков: доступно {available}"
            return {
                "requested": 0, "free_slots": free_slots, "available_recyclers": available,
                "observations": [], "results": [], "candidates": 0, "ready": 0,
                "error": reason, "error_kind": "capacity",
            }

        observations: list[AsteroidObservation] = []
        results: list[dict[str, Any]] = []
        attempted_coords: set[str] = set()
        next_system = int(start_system)
        first_pass = True
        exhausted = False
        error: str | None = None
        error_kind: str | None = None

        while not error and len(results) < requested and next_system >= int(end_system):
            missing = requested - len(results)
            wanted = requested if first_pass else missing
            remaining_capacity = MAX_ASTEROID_CANDIDATES - len(observations)
            if remaining_capacity <= 0:
                break
            batch_limit = min(remaining_capacity, self.asteroid_candidate_limit(wanted))
            batch, next_system, exhausted = await self._scan_asteroid_batch(
                home=home,
                galaxy=galaxy,
                start_system=next_system,
                end_system=end_system,
                limit=batch_limit,
                cancelled=cancelled,
                progress=progress,
            )
            first_pass = False
            if cancelled and cancelled():
                error = "Операция остановлена пользователем"
                error_kind = "cancelled"
                break
            unique_batch: list[AsteroidObservation] = []
            for observation in batch:
                if observation.coord in attempted_coords:
                    continue
                attempted_coords.add(observation.coord)
                observations.append(observation)
                unique_batch.append(observation)
            for observation in unique_batch:
                if len(results) >= requested:
                    break
                if progress:
                    missing = requested - len(results)
                    progress(
                        f"Система {observation.s} · Кандидатов: {len(observations)} · "
                        f"Готово: {len(results)} / {requested} · Продолжается добор ещё {missing} целей"
                    )
                try:
                    results.append(await self.send_asteroid(
                        observation, recycler_count, home, safety_seconds
                    ))
                except UnverifiedSendError as exc:
                    results.append(exc.result)
                    error = str(exc)
                    error_kind = "unverified"
                    break
                except CaptchaRequiredError as exc:
                    error = str(exc)
                    error_kind = "captcha"
                    break
                except BrowserAutomationError as exc:
                    if self._is_skippable_asteroid_error(str(exc)):
                        observation.status = "skipped"
                        observation.error = str(exc)
                        if progress:
                            progress(f"Пропуск {observation.coord}: {exc}")
                        continue
                    error = str(exc)
                    error_kind = "send"
                    break
                except Exception as exc:
                    error = str(exc)
                    error_kind = "send"
                    break
            if exhausted:
                break

        if not observations and not error:
            error = "Астероиды не найдены"
            error_kind = "no_asteroids"
        if not error and len(results) < requested:
            error = f"Удалось отправить только {len(results)} из {requested}: подходящие астероиды закончились"
            error_kind = "not_enough_valid"
        return {
            "requested": requested,
            "free_slots": free_slots,
            "available_recyclers": available,
            "observations": observations,
            "results": results,
            "candidates": len(observations),
            "ready": len(results),
            "error": error,
            "error_kind": error_kind,
        }

    async def import_reports(self, max_pages: int = 100) -> list[SpyReport]:
        page = await self._select_nemexia_page(create_if_missing=True)
        if "options.php" not in page.url:
            await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.locator("#mainFrame").wait_for(state="attached", timeout=15_000)
        except Exception as exc:
            await self._diagnostic("messages_not_open")
            raise BrowserAutomationError("Страница сообщений не открылась") from exc

        async def load_index(index: int) -> None:
            await page.evaluate(
                """index => {
                  if (typeof loadTabContent !== 'function') throw new Error('loadTabContent missing');
                  loadTabContent('TabAdministrative', 2, index);
                }""", index
            )
            await asyncio.sleep(0.75)
            await page.locator("#messagesList").wait_for(state="attached", timeout=10_000)

        try:
            await load_index(0)
        except Exception:
            # The desired tab may already be open, so scrape what is visible.
            pass
        page_count = await page.evaluate(
            r"""() => {
              const indices=[0];
              document.querySelectorAll('.pagination a').forEach(a => {
                const m=(a.getAttribute('onclick')||'').match(/loadTabContent\('TabAdministrative',\s*2,\s*(\d+)\)/);
                if(m) indices.push(Number(m[1]));
              });
              return Math.max(...indices)+1;
            }"""
        )
        page_count = min(max(1, int(page_count or 1)), max_pages)
        collected: dict[str, SpyReport] = {}
        for index in range(page_count):
            if index > 0:
                await load_index(index)
            raw = await page.evaluate(
                r"""() => Array.from(document.querySelectorAll('#messagesList .messageItem')).map(item => {
                  const body=item.querySelector('.messageBody');
                  if(!body) return null;
                  const heading=(body.querySelector('b')?.textContent||body.textContent||'').replace(/\s+/g,' ').trim();
                  if(!/шпионск/i.test(heading)) return null;
                  const coordMatch=heading.match(/(\d+)\s*[:\-]\s*(\d+)\s*[:\-]\s*(\d+)/);
                  if(!coordMatch) return null;
                  const playerMatch=heading.match(/\(\s*([^\)]+?)\s*\)/);
                  const values={};
                  body.querySelectorAll('tr').forEach(row => {
                    const c=row.querySelectorAll('td');
                    if(c.length>=2) values[c[0].textContent.trim().toLowerCase()]=c[1].textContent.replace(/[^0-9]/g,'');
                  });
                  return {
                    coord:[coordMatch[1],coordMatch[2],coordMatch[3]].join(':'),
                    player:playerMatch?playerMatch[1].trim():'—', energy:Number(values['энергия']||0),
                    date:item.querySelector('.messageDate')?.textContent?.trim()||'',
                    messageId:(body.id||'').replace('body-','')
                  };
                }).filter(x=>x&&x.energy>0)"""
            )
            for item in raw:
                report_at = None
                try:
                    report_at = datetime.strptime(item.get("date") or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc_now().tzinfo)
                except Exception:
                    pass
                collected[item["coord"]] = SpyReport(
                    coord=item["coord"], player=item.get("player") or "—", energy=int(item["energy"]),
                    report_at=report_at, message_id=item.get("messageId"),
                )
        return list(collected.values())

    async def _message_page_html(self, page: Page, tab_id: str, message_type: int, index: int) -> str:
        """Load a message page through the game's own read-only tab loader."""
        await page.evaluate(
            """args => {
                const [tab, type, pageIndex] = args;
                if (typeof loadTabContent !== 'function') throw new Error('loadTabContent missing');
                loadTabContent(tab, type, pageIndex);
                if (typeof showTab === 'function') showTab(tab);
            }""", [tab_id, message_type, index]
        )
        try:
            await page.wait_for_function(
                """args => {
                    const [tab, pageIndex] = args;
                    return !!(window.typeHandler && window.typeHandler[tab]
                      && Object.prototype.hasOwnProperty.call(window.typeHandler[tab], pageIndex));
                }""", arg=[tab_id, index], timeout=15_000,
            )
        except Exception as exc:
            await self._diagnostic(f"messages_{tab_id}_{index}")
            raise BrowserAutomationError(f"Не загрузилась страница {index + 1} раздела сообщений") from exc
        return await page.evaluate("tab => document.querySelector('#' + tab + 'Box')?.innerHTML || ''", tab_id)

    @staticmethod
    def _message_page_indices(html: str, tab_id: str, message_type: int) -> list[int]:
        pattern = re.compile(
            rf"loadTabContent\(['\"]{re.escape(tab_id)}['\"],\s*{message_type},\s*(\d+)\)"
        )
        return sorted({int(match.group(1)) for match in pattern.finditer(html)})

    async def _collect_message_pages(
        self, tab_id: str, message_type: int, parser, max_pages: int = 50,
        cancelled: Callable[[], bool] | None = None, not_before: datetime | None = None,
    ) -> list[Any]:
        page = await self._select_nemexia_page(create_if_missing=True)
        if "options.php" not in page.url:
            await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=30_000)
        seen_hashes: set[str] = set()
        seen_indices: set[int] = set()
        pending = [0]
        collected: list[Any] = []
        visited = 0
        while pending and visited < max_pages:
            if cancelled and cancelled():
                break
            index = pending.pop(0)
            if index in seen_indices:
                continue
            seen_indices.add(index)
            html = await self._message_page_html(page, tab_id, message_type, index)
            digest = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
            if digest in seen_hashes:
                break
            seen_hashes.add(digest)
            visited += 1
            if not html.strip():
                break
            parsed = parser(html)
            if not_before:
                dated = [item for item in parsed if item.report_at and item.report_at >= not_before]
                collected.extend(dated)
                # Message pages are ordered newest-first. A page containing dated
                # records only before the boundary cannot yield newer reports later.
                if parsed and not dated and all(item.report_at is not None for item in parsed):
                    break
            else:
                collected.extend(parsed)
            for next_index in self._message_page_indices(html, tab_id, message_type):
                if next_index not in seen_indices and next_index not in pending and next_index < max_pages:
                    pending.append(next_index)
        return collected

    async def collect_combat_reports(self, max_pages: int = 50, cancelled: Callable[[], bool] | None = None,
                                     lookback_hours: int | None = 24) -> list[CombatReport]:
        not_before = utc_now() - timedelta(hours=max(1, lookback_hours)) if lookback_hours else None
        return await self._collect_message_pages("TabReports", 3, parse_battle_reports_html, max_pages, cancelled, not_before)

    async def collect_spy_reports(self, max_pages: int = 50, cancelled: Callable[[], bool] | None = None) -> list[SpyReport]:
        return await self._collect_message_pages("TabAdministrative", 2, parse_spy_reports_html, max_pages, cancelled)

    async def request_all_spy_reports(self) -> None:
        """Game-changing POST. UI must obtain explicit user confirmation before calling it."""
        page = await self._ensure_fleets_page()
        await page.evaluate(
            """() => {
                if (typeof processSpy !== 'function') throw new Error('processSpy missing');
                processSpy(0);
            }"""
        )

    async def delete_spy_messages(self, message_ids: list[str]) -> int:
        """Delete only selected System messages. Caller must obtain explicit UI confirmation."""
        ids = [str(value) for value in dict.fromkeys(message_ids) if str(value).strip()]
        if not ids:
            return 0
        page = await self._select_nemexia_page(create_if_missing=True)
        if "options.php" not in page.url:
            await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=30_000)
        deleted = 0
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            await page.evaluate(
                """ids => new Promise((resolve, reject) => {
                    if (!window.$) { reject(new Error('jQuery missing')); return; }
                    $.post('ajax_messages.php', {
                        option: 'deleteSelectedMessages', type: 2, messages: ids.join(',')
                    }).done(() => resolve()).fail((_, status) => reject(new Error(status || 'delete failed')));
                })""", batch,
            )
            deleted += len(batch)
        return deleted
