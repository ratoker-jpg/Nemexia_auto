from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import browser as browser_module
from browser import BrowserAutomationError, BrowserWorker, find_yandex_browser
from config import FLEETS_URL, GALAXY_URL, GAME_HOST, PROFILE_DIR


_INSTALLED = False


def _background_yandex_command(executable: Path, port: int) -> list[str]:
    """Build the dedicated Yandex command without background throttling.

    The browser remains an ordinary visible browser so CAPTCHA can still be handled
    manually, but once the user minimizes it Playwright does not need to foreground it.
    """
    return [
        str(executable),
        f"--remote-debugging-port={int(port)}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        FLEETS_URL,
    ]


def launch_yandex_background(port: int) -> subprocess.Popen[Any]:
    executable = find_yandex_browser()
    if executable is None:
        raise BrowserAutomationError("Яндекс Браузер не найден в стандартных папках")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    command = _background_yandex_command(executable, port)
    try:
        return subprocess.Popen(command, cwd=PROFILE_DIR)
    except OSError as exc:
        raise BrowserAutomationError(f"Не удалось запустить Яндекс Браузер: {exc}") from exc


async def _ensure_fleets_page_background(self: BrowserWorker):
    """Open/prepare fleets without activating the browser window."""
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
    return page


async def _ensure_galaxy_page_background(
    self: BrowserWorker,
    home: tuple[int, int, int],
    galaxy: int,
    solar: int,
):
    """Open/prepare galaxy without activating the browser window."""
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
    await self._load_galaxy_system(page, galaxy, solar)
    return page


def install_background_browser_fix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # app.py imports launch_yandex from browser.py after this installer runs, so it
    # receives the background-friendly launcher automatically.
    browser_module.launch_yandex = launch_yandex_background
    BrowserWorker._ensure_fleets_page = _ensure_fleets_page_background
    BrowserWorker._ensure_galaxy_page = _ensure_galaxy_page_background
    _INSTALLED = True
