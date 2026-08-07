from __future__ import annotations

import unittest

from visual_system import (
    ACCENT,
    BORDER_1,
    BUTTON_SIZES,
    ERROR,
    SUCCESS,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    WARNING,
    tree_column_anchor,
)


class VisualSystemContractTests(unittest.TestCase):
    def test_orbital_command_core_palette(self) -> None:
        self.assertEqual(SURFACE_0, "#080d16")
        self.assertEqual(SURFACE_1, "#0b1220")
        self.assertEqual(SURFACE_2, "#101a2a")
        self.assertEqual(SURFACE_3, "#17243a")
        self.assertEqual(BORDER_1, "#24334a")
        self.assertEqual(TEXT_1, "#f1f6ff")
        self.assertEqual(ACCENT, "#4f8cff")
        self.assertEqual(SUCCESS, "#4ed69a")
        self.assertEqual(WARNING, "#ffc15a")
        self.assertEqual(ERROR, "#ff7180")

    def test_tree_alignment_is_semantic(self) -> None:
        for column in ("player", "notes", "error", "status"):
            self.assertEqual(tree_column_anchor(column), "w")
        for column in ("energy", "metal", "minerals", "resource_gas", "total", "count"):
            self.assertEqual(tree_column_anchor(column), "e")
        for column in ("coord", "target", "arrival", "return", "spy_at"):
            self.assertEqual(tree_column_anchor(column), "center")

    def test_compact_buttons_are_visually_smaller(self) -> None:
        self.assertLess(BUTTON_SIZES["compact"]["padx"], BUTTON_SIZES["regular"]["padx"])
        self.assertLess(BUTTON_SIZES["compact"]["pady"], BUTTON_SIZES["regular"]["pady"])


if __name__ == "__main__":
    unittest.main()
