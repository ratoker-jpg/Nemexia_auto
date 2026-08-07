from __future__ import annotations

import inspect
from pathlib import Path
import unittest

import tk_layout_compat


ROOT = Path(__file__).resolve().parents[1]


class TkLayoutCompatTests(unittest.TestCase):
    def test_tuple_padding_becomes_scalar(self) -> None:
        self.assertEqual(tk_layout_compat.normalize_classic_padding((0, 12)), 12)
        self.assertEqual(tk_layout_compat.normalize_classic_padding((8, 0)), 8)
        self.assertEqual(tk_layout_compat.normalize_classic_padding((4, 16)), 16)

    def test_scalar_padding_is_unchanged(self) -> None:
        self.assertEqual(tk_layout_compat.normalize_classic_padding(12), 12)
        self.assertEqual(tk_layout_compat.normalize_classic_padding("8"), "8")

    def test_bootstrap_installs_compat_before_visual_foundation(self) -> None:
        source = (ROOT / "app_entry.py").read_text(encoding="utf-8")
        compat = source.index("install_tk_layout_compat()")
        foundation = source.index("prepare_visual_system(app_module)")
        self.assertLess(compat, foundation)

    def test_compat_layer_does_not_touch_business_modules(self) -> None:
        source = inspect.getsource(tk_layout_compat)
        for forbidden in (
            "browser",
            "storage",
            "models",
            "asteroids",
            "Database",
            "BrowserWorker",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
