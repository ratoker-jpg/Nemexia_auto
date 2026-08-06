from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from browser import BrowserAutomationError, UnverifiedSendError
from raid_verification_fix import _parse_send_response, _send_raid_once


class FakeButton:
    def __init__(self, disabled: bool) -> None:
        self.disabled = disabled
        self.clicked = False

    async def is_disabled(self) -> bool:
        return self.disabled

    async def click(self) -> None:
        self.clicked = True


class FakePage:
    def __init__(self, button: FakeButton) -> None:
        self.button = button

    def locator(self, selector: str):
        assert selector == "#SendFleetButton"
        return self.button


class FakeWorker:
    def __init__(self, button: FakeButton) -> None:
        self.page = FakePage(button)
        self.diagnostics: list[str] = []

    async def _prepare_fleet(self, _page, _ship_count, _home):
        return "3:39:11"

    async def _set_target(self, _page, _target):
        return {"one": 60, "round": 120, "gas": 10}

    async def _read_flights_from_page(self, _page):
        return []

    async def _visible_error(self, _page):
        return ""

    async def _diagnostic(self, label: str):
        self.diagnostics.append(label)


class RaidVerificationFixTest(unittest.TestCase):
    def test_response_parser_accepts_only_explicit_value(self) -> None:
        self.assertEqual(_parse_send_response('{"pass":1,"info":"ok"}'), ("1", "ok"))
        self.assertEqual(_parse_send_response('{"pass":0,"info":"bad"}'), ("0", "bad"))
        self.assertEqual(_parse_send_response('<html>failure</html>'), (None, ""))

    def test_disabled_button_is_not_clicked_or_unlocked(self) -> None:
        button = FakeButton(disabled=True)
        worker = FakeWorker(button)
        target = SimpleNamespace(coord="3:1:1", player="Target")
        with self.assertRaisesRegex(BrowserAutomationError, "не разрешает отправку"):
            asyncio.run(_send_raid_once(worker, worker.page, target, 25, (3, 39, 11)))
        self.assertFalse(button.clicked)
        self.assertEqual(worker.diagnostics, ["raid_send_disabled"])

    def test_unknown_response_class_is_fail_closed(self) -> None:
        self.assertTrue(issubclass(UnverifiedSendError, BrowserAutomationError))
        pass_value, _ = _parse_send_response('{"status":"maybe"}')
        self.assertIsNone(pass_value)


if __name__ == "__main__":
    unittest.main()
