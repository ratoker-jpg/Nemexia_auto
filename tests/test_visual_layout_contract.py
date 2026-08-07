from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_SOURCE = (ROOT / "visual_layout.py").read_text(encoding="utf-8")
ENTRY_SOURCE = (ROOT / "app_entry.py").read_text(encoding="utf-8")


class VisualLayoutContractTests(unittest.TestCase):
    def test_layout_module_stays_presentation_only(self) -> None:
        for forbidden in (
            "from browser import",
            "import browser",
            "from storage import",
            "import storage",
            "from models import",
            "import models",
            "from asteroids import",
            "import asteroids",
        ):
            self.assertNotIn(forbidden, LAYOUT_SOURCE)

    def test_required_navigation_keys_are_preserved(self) -> None:
        for key in (
            '"dashboard"',
            '"queue"',
            '"active"',
            '"asteroids"',
            '"debris"',
            '"recon"',
            '"targets"',
            '"history"',
            '"settings"',
            '"logs"',
        ):
            self.assertIn(key, LAYOUT_SOURCE)

    def test_queue_and_dashboard_bindings_are_preserved(self) -> None:
        self.assertIn('self.dashboard_tree.bind("<Double-1>"', LAYOUT_SOURCE)
        self.assertIn('self.queue_tree.bind("<Button-1>", self._toggle_queue_checkbox)', LAYOUT_SOURCE)

    def test_existing_actions_are_still_wired(self) -> None:
        for callback in (
            "self.import_from_browser",
            "self.calculate_times",
            "self.generate_queue",
            "self.send_next",
            "self.prepare_selected_queue",
            "self.send_wave",
            "self.reset_stuck_sending",
            "self.move_queue(-1)",
            "self.move_queue(1)",
            "self.remove_queue_selected",
            "self.clear_queue",
            "self.scan_asteroids_manual",
            "self.calculate_asteroid_wave",
            "self.send_asteroid_wave",
            "self.toggle_asteroid_auto",
            "self.cancel_asteroid_operation",
            "self.scan_debris_asteroids",
            "self.send_selected_debris_asteroids",
            "self.cancel_debris_operation",
            "self.save_settings",
            "self.manual_backup",
            "self.open_data_dir",
            "self.show_build_info",
        ):
            self.assertIn(callback, LAYOUT_SOURCE)

    def test_bootstrap_installs_layout_before_debris_feature_wrapper(self) -> None:
        foundation = ENTRY_SOURCE.index("install_visual_system(app_module, BaseRaidManagerApp)")
        layout = ENTRY_SOURCE.index("install_visual_layout(BaseRaidManagerApp)")
        debris_layout = ENTRY_SOURCE.index("install_debris_layout(debris_module)")
        debris_feature = ENTRY_SOURCE.index("debris_module.install_debris_asteroid_feature(BaseRaidManagerApp)")
        self.assertLess(foundation, layout)
        self.assertLess(layout, debris_layout)
        self.assertLess(debris_layout, debris_feature)


if __name__ == "__main__":
    unittest.main()
