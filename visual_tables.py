from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk


WIDE_TABLE_MIN_WIDTH = 850
ASTEROID_COMPACT_WIDTH = 1050
SIDEBAR_COMPACT_WIDTH = 1250
SIDEBAR_REGULAR_PX = 220
SIDEBAR_COMPACT_PX = 208

_INSTALLED_CLASSES: set[type[Any]] = set()


def wide_table_required(columns: tuple[str, ...], widths: dict[str, int]) -> bool:
    """Return whether preserving declared column widths needs horizontal scrolling."""
    total_width = sum(int(widths.get(column, 100)) for column in columns)
    return len(columns) >= 8 or total_width >= WIDE_TABLE_MIN_WIDTH


def asteroid_kpi_layout(width: int) -> tuple[tuple[int, int, int], ...]:
    """Return row/column/columnspan positions for the five asteroid KPI cards."""
    if int(width) < ASTEROID_COMPACT_WIDTH:
        return (
            (0, 0, 2),
            (0, 2, 2),
            (0, 4, 2),
            (1, 0, 3),
            (1, 3, 3),
        )
    return (
        (0, 0, 1),
        (0, 1, 1),
        (0, 2, 1),
        (0, 3, 1),
        (0, 4, 1),
    )


def _find_asteroid_kpi_grid(page: tk.Misc) -> tuple[tk.Misc | None, list[tk.Misc]]:
    for child in page.winfo_children():
        gridded = [widget for widget in child.winfo_children() if widget.grid_info()]
        if len(gridded) != 5:
            continue
        try:
            ordered = sorted(gridded, key=lambda widget: int(widget.grid_info().get("column", 0)))
        except Exception:
            ordered = gridded
        return child, ordered
    return None, []


def _apply_asteroid_kpi_layout(container: tk.Misc, cards: list[tk.Misc], width: int) -> None:
    positions = asteroid_kpi_layout(width)
    compact = int(width) < ASTEROID_COMPACT_WIDTH

    for column in range(6):
        container.grid_columnconfigure(column, weight=1 if compact or column < 5 else 0)
    for row in range(2):
        container.grid_rowconfigure(row, weight=1)

    for card in cards:
        card.grid_forget()

    for index, (card, (row, column, span)) in enumerate(zip(cards, positions)):
        if compact:
            padx = 4
            pady = (0, 8) if row == 0 else (0, 0)
        else:
            padx = (0, 8) if index == 0 else ((8, 0) if index == 4 else 8)
            pady = 0
        card.grid(
            row=row,
            column=column,
            columnspan=span,
            sticky="nsew",
            padx=padx,
            pady=pady,
        )


def install_tables_dpi(app_class: type[Any]) -> None:
    """Install table scrolling/sort affordances and compact-width presentation only."""
    if app_class in _INSTALLED_CLASSES:
        return

    original_tree = app_class._tree
    original_sort_tree = app_class._sort_tree
    original_build_shell = app_class._build_shell
    original_build_asteroids_page = app_class._build_asteroids_page

    def tree(
        self: Any,
        parent: tk.Misc,
        columns: tuple[str, ...],
        headings: dict[str, str],
        widths: dict[str, int],
        selectmode: str = "browse",
    ) -> tuple[ttk.Treeview, ttk.Scrollbar]:
        view, vertical = original_tree(self, parent, columns, headings, widths, selectmode)
        view._orbital_heading_text = {  # type: ignore[attr-defined]
            column: headings.get(column, column) for column in columns
        }
        view._orbital_sort_column = None  # type: ignore[attr-defined]

        wide = wide_table_required(columns, widths)
        for column in columns:
            # Wide data tables preserve their audited widths and scroll instead of
            # compressing every column into an unreadable strip.
            view.column(column, stretch=not wide)

        if wide:
            horizontal = ttk.Scrollbar(parent, orient="horizontal", command=view.xview)
            view.configure(xscrollcommand=horizontal.set)
            horizontal.pack(side="bottom", fill="x")
            view._orbital_horizontal_scrollbar = horizontal  # type: ignore[attr-defined]
        return view, vertical

    def sort_tree(self: Any, view: ttk.Treeview, column: str) -> None:
        # Delegate the actual ordering to the unchanged production implementation.
        original_sort_tree(self, view, column)

        base_headings = getattr(view, "_orbital_heading_text", {})
        state = getattr(self, "_tree_sort_state", {})
        reverse = bool(state.get((str(view), column), False))
        indicator = "▼" if reverse else "▲"
        for current, label in base_headings.items():
            text = f"{label} {indicator}" if current == column else label
            view.heading(current, text=text)
        view._orbital_sort_column = column  # type: ignore[attr-defined]

    def build_asteroids_page(self: Any) -> None:
        original_build_asteroids_page(self)
        page = self.pages.get("asteroids")
        if page is None:
            return
        container, cards = _find_asteroid_kpi_grid(page)
        if container is None or len(cards) != 5:
            return

        self._asteroid_kpi_grid = container
        self._asteroid_kpi_cards = cards
        self._asteroid_kpi_compact = None

        def reflow(event: tk.Event | None = None) -> None:
            width = int(event.width) if event is not None else int(page.winfo_width())
            compact = width < ASTEROID_COMPACT_WIDTH
            if self._asteroid_kpi_compact is compact:
                return
            self._asteroid_kpi_compact = compact
            _apply_asteroid_kpi_layout(container, cards, width)

        page.bind("<Configure>", reflow, add="+")
        self.after_idle(reflow)

    def build_shell(self: Any) -> None:
        original_build_shell(self)

        # Keep the same minimum window contract while recovering a little content
        # width on 1120/1366 layouts. This changes only sidebar pixels.
        sidebar = getattr(self, "sidebar", None)

        def resize_shell(event: tk.Event) -> None:
            if event.widget is not self or sidebar is None:
                return
            desired = SIDEBAR_COMPACT_PX if int(event.width) < SIDEBAR_COMPACT_WIDTH else SIDEBAR_REGULAR_PX
            try:
                current = int(float(sidebar.cget("width")))
            except Exception:
                current = 0
            if current != desired:
                sidebar.configure(width=desired)

        self.bind("<Configure>", resize_shell, add="+")

        # Named fonts already follow Windows DPI. Give table rows a small capped
        # increase so 125–200% text never clips while retaining control-panel density.
        try:
            tk_scaling = float(self.tk.call("tk", "scaling"))
        except Exception:
            tk_scaling = 96.0 / 72.0
        dpi_factor = max(1.0, min(1.20, tk_scaling / (96.0 / 72.0)))
        ttk.Style(self).configure("Dark.Treeview", rowheight=int(round(38 * dpi_factor)))

    app_class._tree = tree
    app_class._sort_tree = sort_tree
    app_class._build_asteroids_page = build_asteroids_page
    app_class._build_shell = build_shell
    _INSTALLED_CLASSES.add(app_class)
