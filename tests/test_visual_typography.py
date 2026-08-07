from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VisualTypographyTests(unittest.TestCase):
    def test_type_scale_is_quieter_and_more_readable(self) -> None:
        source = (ROOT / "visual_typography.py").read_text(encoding="utf-8")
        for expected in (
            'FONT_DISPLAY: ("Segoe UI", 11, "bold")',
            'FONT_PAGE_TITLE: ("Segoe UI", 18, "bold")',
            'FONT_SECTION_TITLE: ("Segoe UI", 10, "bold")',
            'FONT_METRIC: ("Segoe UI", 20, "bold")',
            'FONT_BODY_STRONG: ("Segoe UI", 10, "bold")',
            'FONT_BODY: ("Segoe UI", 10, "normal")',
            'FONT_CAPTION: ("Segoe UI", 9, "normal")',
            'FONT_MONO: ("Consolas", 9, "normal")',
        ):
            self.assertIn(expected, source)

    def test_typography_wraps_only_style_configuration(self) -> None:
        source = (ROOT / "visual_typography.py").read_text(encoding="utf-8")
        self.assertIn("original_configure_style = app_class._configure_style", source)
        self.assertIn("original_configure_style(self)", source)
        self.assertIn("_apply_typography(self)", source)
        for forbidden in (
            "run_task",
            "send_next",
            "send_wave",
            "BrowserWorker",
            "sqlite",
            "debris",
            "asteroid",
        ):
            self.assertNotIn(forbidden, source)

    def test_typography_installs_after_foundation_before_layout(self) -> None:
        source = (ROOT / "app_entry.py").read_text(encoding="utf-8")
        foundation = source.index("install_visual_system(app_module, BaseRaidManagerApp)")
        typography = source.index("install_typography(BaseRaidManagerApp)")
        layout = source.index("install_visual_layout(BaseRaidManagerApp)")
        self.assertLess(foundation, typography)
        self.assertLess(typography, layout)


if __name__ == "__main__":
    unittest.main()
