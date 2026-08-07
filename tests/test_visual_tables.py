from __future__ import annotations

from pathlib import Path
import unittest

from visual_tables import asteroid_kpi_layout, wide_table_required


ROOT = Path(__file__).resolve().parents[1]
ENTRY_SOURCE = (ROOT / "app_entry.py").read_text(encoding="utf-8")
TABLE_SOURCE = (ROOT / "visual_tables.py").read_text(encoding="utf-8")


class VisualTablesContractTests(unittest.TestCase):
    def test_wide_tables_request_horizontal_scrolling(self) -> None:
        self.assertTrue(
            wide_table_required(
                ("coord", "player", "metal", "minerals", "gas", "total", "time", "status"),
                {},
            )
        )
        self.assertTrue(
            wide_table_required(
                ("player", "coord", "metal"),
                {"player": 300, "coord": 250, "metal": 350},
            )
        )
        self.assertFalse(
            wide_table_required(
                ("player", "coord", "metal"),
                {"player": 160, "coord": 100, "metal": 120},
            )
        )

    def test_asteroid_kpis_reflow_three_plus_two_on_compact_width(self) -> None:
        compact = asteroid_kpi_layout(900)
        self.assertEqual(len(compact), 5)
        self.assertEqual([row for row, _, _ in compact], [0, 0, 0, 1, 1])
        self.assertEqual([span for _, _, span in compact], [2, 2, 2, 3, 3])

    def test_asteroid_kpis_stay_one_row_when_wide(self) -> None:
        regular = asteroid_kpi_layout(1400)
        self.assertEqual([row for row, _, _ in regular], [0, 0, 0, 0, 0])
        self.assertEqual([column for _, column, _ in regular], [0, 1, 2, 3, 4])

    def test_sorting_delegates_to_existing_production_method(self) -> None:
        self.assertIn("original_sort_tree(self, view, column)", TABLE_SOURCE)
        self.assertIn('indicator = "▼" if reverse else "▲"', TABLE_SOURCE)

    def test_bootstrap_keeps_tables_wrapper_before_debris_feature(self) -> None:
        layout = ENTRY_SOURCE.index("install_visual_layout(BaseRaidManagerApp)")
        tables = ENTRY_SOURCE.index("install_tables_dpi(BaseRaidManagerApp)")
        debris_layout = ENTRY_SOURCE.index("install_debris_layout(debris_module)")
        debris_feature = ENTRY_SOURCE.index("debris_module.install_debris_asteroid_feature(BaseRaidManagerApp)")
        self.assertLess(layout, tables)
        self.assertLess(tables, debris_layout)
        self.assertLess(debris_layout, debris_feature)


if __name__ == "__main__":
    unittest.main()
