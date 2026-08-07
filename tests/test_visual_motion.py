from __future__ import annotations

from pathlib import Path
import unittest

from visual_motion import (
    KPI_FLASH_MS,
    NAV_ACCENT_MS,
    STATUS_FLASH_MS,
    blend_hex,
    status_flash_color,
)
from visual_system import ERROR_BG, SUCCESS_BG


ROOT = Path(__file__).resolve().parents[1]
ENTRY_SOURCE = (ROOT / "app_entry.py").read_text(encoding="utf-8")
MOTION_SOURCE = (ROOT / "visual_motion.py").read_text(encoding="utf-8")


class VisualMotionContractTests(unittest.TestCase):
    def test_motion_durations_stay_in_audited_ranges(self) -> None:
        self.assertGreaterEqual(NAV_ACCENT_MS, 100)
        self.assertLessEqual(NAV_ACCENT_MS, 140)
        self.assertGreaterEqual(KPI_FLASH_MS, 150)
        self.assertLessEqual(KPI_FLASH_MS, 200)
        self.assertGreaterEqual(STATUS_FLASH_MS, 200)
        self.assertLessEqual(STATUS_FLASH_MS, 300)

    def test_color_blending_is_deterministic(self) -> None:
        self.assertEqual(blend_hex("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(blend_hex("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(blend_hex("#000000", "#ffffff", 0.5), "#808080")

    def test_status_flash_is_semantic(self) -> None:
        self.assertEqual(status_flash_color("Ошибка подключения"), ERROR_BG)
        self.assertEqual(status_flash_color("Отправлено рейсов: 3"), SUCCESS_BG)
        self.assertIsNone(status_flash_color("Синхронизация рейсов…"))

    def test_motion_uses_after_and_never_sleeps(self) -> None:
        self.assertNotIn("sleep(", MOTION_SOURCE)
        self.assertIn("widget.after(", MOTION_SOURCE)
        self.assertIn("self.after(", MOTION_SOURCE)

    def test_row_hover_adds_bindings_instead_of_replacing_them(self) -> None:
        self.assertIn('view.bind("<Motion>", motion, add="+")', MOTION_SOURCE)
        self.assertIn('view.bind("<Leave>", lambda _: clear(), add="+")', MOTION_SOURCE)

    def test_bootstrap_installs_motion_before_debris_feature_wrapper(self) -> None:
        tables = ENTRY_SOURCE.index("install_tables_dpi(BaseRaidManagerApp)")
        motion = ENTRY_SOURCE.index("install_motion(BaseRaidManagerApp)")
        debris_layout = ENTRY_SOURCE.index("install_debris_layout(debris_module)")
        debris_feature = ENTRY_SOURCE.index("debris_module.install_debris_asteroid_feature(BaseRaidManagerApp)")
        self.assertLess(tables, motion)
        self.assertLess(motion, debris_layout)
        self.assertLess(debris_layout, debris_feature)


if __name__ == "__main__":
    unittest.main()
