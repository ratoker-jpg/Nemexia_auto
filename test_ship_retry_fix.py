from __future__ import annotations

import asyncio
import unittest

from browser import BrowserWorker
from ship_retry_fix import install_ship_retry_fix


class FakeLocator:
    def __init__(self, selector: str, waits: list[tuple[str, str]]) -> None:
        self.selector = selector
        self.waits = waits

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self.waits.append((self.selector, state))


class FakePage:
    def __init__(self) -> None:
        self.waits: list[tuple[str, str]] = []
        self.script = ""

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector, self.waits)

    async def evaluate(self, script: str) -> bool:
        self.script = script
        return True


class ShipRetryFixTest(unittest.TestCase):
    def setUp(self) -> None:
        install_ship_retry_fix()

    def test_exact_game_message_is_retryable(self) -> None:
        self.assertTrue(BrowserWorker._is_no_ships_error("Вы должны выбрать корабли"))
        self.assertTrue(BrowserWorker._is_no_ships_error("Ошибка игры: Вы должны выбрать корабли"))
        self.assertFalse(BrowserWorker._is_no_ships_error("Недостаточно газа"))

    def test_popup_is_acknowledged_and_back_is_requested(self) -> None:
        page = FakePage()
        worker = object.__new__(BrowserWorker)
        result = asyncio.run(worker._dismiss_no_ships_popup_and_return(page))

        self.assertTrue(result)
        self.assertEqual(
            page.waits,
            [("#dialogMessage", "visible"), ("#TabChooseShips", "visible")],
        )
        self.assertIn("вы должны выбрать корабли", page.script)
        self.assertIn("#dlg_ok", page.script)
        self.assertIn("label === 'ок'", page.script)
        self.assertIn("=== 'назад'", page.script)


if __name__ == "__main__":
    unittest.main()
