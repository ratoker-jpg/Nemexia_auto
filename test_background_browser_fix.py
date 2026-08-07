from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from background_browser_fix import (
    _background_yandex_command,
    _ensure_fleets_page_background,
    _ensure_galaxy_page_background,
)


class _FakeLocator:
    async def wait_for(self, **kwargs):
        return None


class _FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.front_calls = 0
        self.goto_calls: list[str] = []

    def locator(self, selector: str):
        return _FakeLocator()

    async def goto(self, url: str, **kwargs):
        self.url = url
        self.goto_calls.append(url)

    async def bring_to_front(self):
        self.front_calls += 1
        raise AssertionError("background operation must not call bring_to_front")


class _FakeWorker:
    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.loaded: list[tuple[int, int]] = []

    async def _select_nemexia_page(self, create_if_missing=False):
        return self.page

    async def _assert_no_captcha(self, page, label):
        return None

    async def _diagnostic(self, label):
        return None

    async def _select_planet(self, page, home):
        return ":".join(map(str, home))

    async def _load_galaxy_system(self, page, galaxy, solar):
        self.loaded.append((galaxy, solar))


class BackgroundBrowserFixTest(unittest.TestCase):
    def test_launcher_disables_background_throttling(self) -> None:
        command = _background_yandex_command(Path("C:/Yandex/browser.exe"), 9222)
        self.assertIn("--disable-background-timer-throttling", command)
        self.assertIn("--disable-backgrounding-occluded-windows", command)
        self.assertIn("--disable-renderer-backgrounding", command)
        self.assertNotIn("--start-maximized", command)

    def test_fleets_page_does_not_foreground_browser(self) -> None:
        page = _FakePage("https://game.ares.nemexia.com/fleets.php")
        worker = _FakeWorker(page)
        result = asyncio.run(_ensure_fleets_page_background(worker))
        self.assertIs(result, page)
        self.assertEqual(page.front_calls, 0)

    def test_galaxy_page_does_not_foreground_browser(self) -> None:
        page = _FakePage("https://game.ares.nemexia.com/galaxy.php?galaxy=3&solar=39")
        worker = _FakeWorker(page)
        result = asyncio.run(_ensure_galaxy_page_background(worker, (3, 39, 8), 3, 38))
        self.assertIs(result, page)
        self.assertEqual(page.front_calls, 0)
        self.assertEqual(worker.loaded, [(3, 38)])


if __name__ == "__main__":
    unittest.main()
