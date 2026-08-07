from __future__ import annotations

from typing import Any


_INSTALLED_CLASSES: set[type[Any]] = set()


def _renumber_queue_rows(app: Any) -> None:
    """Show 1..N row numbers without changing stored queue positions or IDs."""
    tree = getattr(app, "queue_tree", None)
    if tree is None:
        return
    try:
        columns = tuple(tree.cget("columns"))
        position_index = columns.index("position")
    except Exception:
        return

    for row_number, iid in enumerate(tree.get_children(""), start=1):
        try:
            values = list(tree.item(iid, "values"))
            if position_index >= len(values):
                continue
            values[position_index] = row_number
            tree.item(iid, values=values)
        except Exception:
            continue


def install_queue_row_numbering(app_class: type[Any]) -> None:
    """Keep queue '#' as a display row number, independent from DB position."""
    if app_class in _INSTALLED_CLASSES:
        return

    original_render_queue = app_class.render_queue
    original_sort_tree = app_class._sort_tree

    def render_queue(self: Any) -> None:
        original_render_queue(self)
        _renumber_queue_rows(self)

    def sort_tree(self: Any, tree: Any, column: str, reverse: bool = False) -> None:
        original_sort_tree(self, tree, column, reverse)
        if tree is getattr(self, "queue_tree", None):
            _renumber_queue_rows(self)

    app_class.render_queue = render_queue
    app_class._sort_tree = sort_tree
    _INSTALLED_CLASSES.add(app_class)
