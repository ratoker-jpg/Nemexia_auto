from __future__ import annotations

import asyncio
import unittest

from bound_tab_fix import _bound_page_is_valid, _choose_active_game_page


class FakePage:
    def __init__(self, url: str, *, focused: bool = False, visible: bool = False, closed: bool = False) -> None:
        self.url = url
        self.focused = focused
        self.visible = visible
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed

    async def evaluate(self, _script: str):
        return {"focused": self.focused, "visible": self.visible}


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(pages)]


class FakeWorker:
    def __init__(self, pages):
        self._browser = FakeBrowser(pages)


class BoundTabFixTest(unittest.TestCase):
    def test_focused_game_page_wins(self) -> None:
        first = FakePage("https://game.ares.nemexia.com/fleets.php", visible=True)
        second = FakePage("https://game.ares.nemexia.com/galaxy.php", focused=True, visible=True)
        selected = asyncio.run(_choose_active_game_page(FakeWorker([first, second])))
        self.assertIs(selected, second)

    def test_single_visible_game_page_is_selected(self) -> None:
        first = FakePage("https://game.ares.nemexia.com/fleets.php", visible=False)
        second = FakePage("https://game.ares.nemexia.com/galaxy.php", visible=True)
        selected = asyncio.run(_choose_active_game_page(FakeWorker([first, second])))
        self.assertIs(selected, second)

    def test_ambiguous_multiple_tabs_stop(self) -> None:
        pages = [
            FakePage("https://game.ares.nemexia.com/fleets.php", visible=True),
            FakePage("https://game.ares.nemexia.com/galaxy.php", visible=True),
        ]
        with self.assertRaisesRegex(Exception, "несколько активных вкладок"):
            asyncio.run(_choose_active_game_page(FakeWorker(pages)))

    def test_closed_bound_page_is_invalid(self) -> None:
        page = FakePage("https://game.ares.nemexia.com/fleets.php", closed=True)
        self.assertFalse(_bound_page_is_valid(FakeWorker([page]), page))


if __name__ == "__main__":
    unittest.main()
