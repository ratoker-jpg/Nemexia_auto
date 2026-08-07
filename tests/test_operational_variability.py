from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OperationalVariabilityTests(unittest.TestCase):
    def test_asteroid_scope_exposes_existing_galaxy_variable(self) -> None:
        source = (ROOT / "operational_variability.py").read_text(encoding="utf-8")
        self.assertIn('"Галактика"', source)
        self.assertIn("self.asteroid_galaxy_var", source)
        self.assertIn("from_=1", source)
        self.assertIn("to=3", source)
        self.assertIn('"Система от"', source)

    def test_existing_asteroid_options_already_drive_browser_scan(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"galaxy": self._safe_int(self.asteroid_galaxy_var, 3)', source)
        self.assertIn('galaxy=int(options["galaxy"])', source)
        self.assertIn('start_system=int(options["start_system"])', source)
        self.assertIn('end_system=int(options["end_system"])', source)

    def test_normal_raids_select_configured_home_before_ship_entry(self) -> None:
        source = (ROOT / "operational_variability.py").read_text(encoding="utf-8")
        select_at = source.index("await self._select_planet(page, home)")
        original_at = source.index("return await original_prepare_fleet")
        self.assertLess(select_at, original_at)
        self.assertIn("FLEETS_URL", source)
        self.assertNotIn("Москва", source)
        self.assertNotIn("Питер", source)

    def test_bootstrap_installs_scope_before_table_wrapper(self) -> None:
        source = (ROOT / "app_entry.py").read_text(encoding="utf-8")
        layout = source.index("install_visual_layout(BaseRaidManagerApp)")
        scope = source.index("install_asteroid_scope_ui(BaseRaidManagerApp)")
        tables = source.index("install_tables_dpi(BaseRaidManagerApp)")
        self.assertLess(layout, scope)
        self.assertLess(scope, tables)
        self.assertIn("install_raid_home_selection(app_module.BrowserWorker)", source)


if __name__ == "__main__":
    unittest.main()
