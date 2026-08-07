from __future__ import annotations

import unittest

from queue_row_numbering import _renumber_queue_rows


class FakeTree:
    def __init__(self) -> None:
        self.rows = {
            "q:10": ["☐", 1, "1:1:1"],
            "q:20": ["☐", 9, "2:2:2"],
            "q:30": ["☐", 13, "3:3:3"],
        }
        self.order = ["q:10", "q:20", "q:30"]

    def cget(self, key: str):
        if key == "columns":
            return ("picked", "position", "coord")
        raise KeyError(key)

    def get_children(self, parent: str = ""):
        return tuple(self.order)

    def item(self, iid: str, option: str | None = None, **kwargs):
        if "values" in kwargs:
            self.rows[iid] = list(kwargs["values"])
            return None
        if option == "values":
            return tuple(self.rows[iid])
        return {"values": tuple(self.rows[iid])}


class FakeApp:
    def __init__(self) -> None:
        self.queue_tree = FakeTree()


class QueueRowNumberingTests(unittest.TestCase):
    def test_stored_positions_are_replaced_only_in_display(self) -> None:
        app = FakeApp()
        _renumber_queue_rows(app)
        self.assertEqual([app.queue_tree.rows[iid][1] for iid in app.queue_tree.order], [1, 2, 3])
        self.assertEqual([app.queue_tree.rows[iid][2] for iid in app.queue_tree.order], ["1:1:1", "2:2:2", "3:3:3"])

    def test_numbers_follow_current_visual_order(self) -> None:
        app = FakeApp()
        app.queue_tree.order = ["q:30", "q:10", "q:20"]
        _renumber_queue_rows(app)
        self.assertEqual(app.queue_tree.rows["q:30"][1], 1)
        self.assertEqual(app.queue_tree.rows["q:10"][1], 2)
        self.assertEqual(app.queue_tree.rows["q:20"][1], 3)


if __name__ == "__main__":
    unittest.main()
