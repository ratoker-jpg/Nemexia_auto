from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from page_capture import capture_current_page


class FakeSession:
    async def send(self, method, payload):
        assert method == "Page.captureSnapshot"
        assert payload == {"format": "mhtml"}
        return {"data": "From: fake\nContent-Type: multipart/related"}

    async def detach(self):
        return None


class FakeContext:
    def __init__(self):
        self.pages = []

    async def new_cdp_session(self, page):
        return FakeSession()


class FakePage:
    def __init__(self, context):
        self.context = context
        self.url = "https://game.ares.nemexia.com/fleets.php"

    def is_closed(self):
        return False

    async def evaluate(self, script):
        return True

    async def title(self):
        return "Nemexia"

    async def content(self):
        return "<html><body>Ошибка игры</body></html>"

    async def screenshot(self, path, full_page):
        assert full_page is True
        Path(path).write_bytes(b"PNG")


class FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]


class FakeWorker:
    def __init__(self):
        context = FakeContext()
        page = FakePage(context)
        context.pages.append(page)
        self._browser = FakeBrowser(context)
        self._page = page


class CaptureCurrentPageTest(unittest.TestCase):
    def test_capture_and_limit(self):
        with tempfile.TemporaryDirectory(prefix="nemexia_snapshot_test_") as temp:
            root = Path(temp)
            worker = FakeWorker()
            for index in range(12):
                result = asyncio.run(capture_current_page(worker, root, keep=10))
                folder = Path(result["folder"])
                self.assertTrue((folder / "screenshot.png").exists())
                self.assertTrue((folder / "page.html").exists())
                self.assertTrue((folder / "page.mhtml").exists())
                metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                self.assertEqual(metadata["title"], "Nemexia")
                # Avoid equal millisecond folder names in this fast fake test.
                if index < 11:
                    asyncio.run(asyncio.sleep(0.002))
            self.assertEqual(len([path for path in root.iterdir() if path.is_dir()]), 10)


if __name__ == "__main__":
    unittest.main()
