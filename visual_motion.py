from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from visual_system import (
    ACCENT,
    BORDER_1,
    ERROR_BG,
    FONT_BODY_STRONG,
    INFO_BG,
    SUCCESS_BG,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_2,
)


NAV_ACCENT_MS = 120
KPI_FLASH_MS = 180
STATUS_FLASH_MS = 260
BUSY_FRAME_MS = 140
ROW_HOVER_BG = "#15243a"

KPI_FLASH_TITLES = {
    "ЗАНЯТО СЛОТОВ",
    "В ОЧЕРЕДИ",
    "ЦЕЛЕЙ ПО МЕТАЛЛУ",
    "КАНДИДАТОВ",
    "ГОТОВО",
    "ОТПРАВЛЕНО",
    "НАЙДЕНО С ОБЛОМКАМИ",
}

_ERROR_WORDS = ("ошибка", "не удалось", "останов", "captcha")
_SUCCESS_WORDS = (
    "подключено",
    "заверш",
    "отправлено",
    "сохранен",
    "сохранён",
    "импортировано",
    "рассчитано",
)

_INSTALLED_CLASSES: set[type[Any]] = set()


def blend_hex(start: str, end: str, ratio: float) -> str:
    """Blend two #RRGGBB colors; presentation helper with no Tk side effects."""
    ratio = max(0.0, min(1.0, float(ratio)))

    def rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        if len(value) != 6:
            raise ValueError("Expected #RRGGBB color")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]

    a = rgb(start)
    b = rgb(end)
    values = tuple(round(left + (right - left) * ratio) for left, right in zip(a, b))
    return "#" + "".join(f"{value:02x}" for value in values)


def status_flash_color(text: str) -> str | None:
    normalized = str(text).casefold()
    if any(word in normalized for word in _ERROR_WORDS):
        return ERROR_BG
    if any(word in normalized for word in _SUCCESS_WORDS):
        return SUCCESS_BG
    return None


def _surface_background(widget: tk.Misc, color: str, include_children: bool) -> None:
    try:
        if isinstance(widget, (tk.Frame, tk.Label)):
            widget.configure(bg=color)
        if include_children:
            for child in widget.winfo_children():
                _surface_background(child, color, True)
    except tk.TclError:
        return


def _cancel_motion(widget: tk.Misc) -> None:
    ids = list(getattr(widget, "_orbital_motion_ids", []))
    for after_id in ids:
        try:
            widget.after_cancel(after_id)
        except (tk.TclError, ValueError):
            pass
    widget._orbital_motion_ids = []  # type: ignore[attr-defined]


def _animate_background(
    widget: tk.Misc,
    start: str,
    end: str,
    duration_ms: int,
    *,
    include_children: bool = False,
    on_finish: Callable[[], None] | None = None,
) -> None:
    _cancel_motion(widget)
    steps = max(3, min(8, int(duration_ms) // 25))
    ids: list[str] = []

    for step in range(steps + 1):
        delay = round(duration_ms * step / steps)
        ratio = step / steps
        color = blend_hex(start, end, ratio)

        def apply(value: str = color, final: bool = step == steps) -> None:
            try:
                _surface_background(widget, value, include_children)
                if final and on_finish is not None:
                    on_finish()
            except tk.TclError:
                return

        try:
            ids.append(widget.after(delay, apply))
        except tk.TclError:
            break
    widget._orbital_motion_ids = ids  # type: ignore[attr-defined]


def _attach_row_hover(view: ttk.Treeview) -> None:
    view.tag_configure("__orbital_hover__", background=ROW_HOVER_BG)
    state = {"iid": ""}

    def clear() -> None:
        iid = state["iid"]
        state["iid"] = ""
        if not iid or not view.exists(iid):
            return
        tags = tuple(tag for tag in view.item(iid, "tags") if tag != "__orbital_hover__")
        view.item(iid, tags=tags)

    def motion(event: tk.Event) -> None:
        iid = view.identify_row(event.y)
        if iid == state["iid"]:
            return
        clear()
        if not iid or not view.exists(iid) or iid in view.selection():
            return
        tags = tuple(view.item(iid, "tags"))
        # Semantic status rows keep their stronger color instead of being obscured.
        if tags:
            return
        view.item(iid, tags=("__orbital_hover__",))
        state["iid"] = iid

    view.bind("<Motion>", motion, add="+")
    view.bind("<Leave>", lambda _: clear(), add="+")


def install_motion(app_class: type[Any]) -> None:
    """Install lightweight after()-only presentation motion."""
    if app_class in _INSTALLED_CLASSES:
        return

    original_card = app_class._card
    original_tree = app_class._tree
    original_show_page = app_class.show_page
    original_build_shell = app_class._build_shell

    def card(self: Any, parent: tk.Misc, title: str, variable: tk.StringVar, subtitle: str) -> tk.Frame:
        frame = original_card(self, parent, title, variable, subtitle)
        if title not in KPI_FLASH_TITLES:
            return frame

        state = {"value": str(variable.get())}

        def changed(*_: object) -> None:
            value = str(variable.get())
            if value == state["value"]:
                return
            state["value"] = value

            def finish() -> None:
                try:
                    frame.configure(highlightbackground=BORDER_1)
                except tk.TclError:
                    pass

            try:
                frame.configure(highlightbackground=ACCENT)
            except tk.TclError:
                return
            _animate_background(
                frame,
                INFO_BG,
                SURFACE_2,
                KPI_FLASH_MS,
                include_children=True,
                on_finish=finish,
            )

        trace_id = variable.trace_add("write", changed)
        frame._orbital_variable_trace = (variable, trace_id)  # type: ignore[attr-defined]
        return frame

    def tree(
        self: Any,
        parent: tk.Misc,
        columns: tuple[str, ...],
        headings: dict[str, str],
        widths: dict[str, int],
        selectmode: str = "browse",
    ) -> tuple[ttk.Treeview, ttk.Scrollbar]:
        view, vertical = original_tree(self, parent, columns, headings, widths, selectmode)
        _attach_row_hover(view)
        return view, vertical

    def show_page(self: Any, key: str) -> None:
        original_show_page(self, key)
        button = self.nav_buttons.get(key)
        rail = getattr(button, "_nav_rail", None) if button is not None else None
        if rail is None:
            return
        try:
            rail.configure(bg=SURFACE_1)
        except tk.TclError:
            return
        _animate_background(rail, SURFACE_1, ACCENT, NAV_ACCENT_MS)

    def build_shell(self: Any) -> None:
        original_build_shell(self)
        status = getattr(self, "status_badge", None)
        if status is None:
            return

        last_status = {"value": str(self.status_var.get())}

        def status_changed(*_: object) -> None:
            text = str(self.status_var.get())
            if text == last_status["value"]:
                return
            last_status["value"] = text
            color = status_flash_color(text)
            if color is None:
                return
            _animate_background(status, color, SURFACE_3, STATUS_FLASH_MS)

        trace_id = self.status_var.trace_add("write", status_changed)
        status._orbital_status_trace = (self.status_var, trace_id)  # type: ignore[attr-defined]

        topbar = status.master
        busy_indicator = tk.Label(
            topbar,
            text="",
            width=3,
            anchor="e",
            bg=SURFACE_0,
            fg=ACCENT,
            font=FONT_BODY_STRONG,
        )
        busy_indicator.pack(side="right", before=status, padx=(0, 4))
        self.busy_indicator = busy_indicator
        busy_frames = ("·", "··", "···")
        busy_state = {"index": 0}

        def tick_busy() -> None:
            if getattr(self, "_closing", False):
                return
            try:
                if bool(getattr(self, "busy", False)):
                    busy_indicator.configure(text=busy_frames[busy_state["index"] % len(busy_frames)])
                    busy_state["index"] += 1
                    delay = BUSY_FRAME_MS
                else:
                    busy_indicator.configure(text="")
                    busy_state["index"] = 0
                    delay = 320
                self._orbital_busy_after = self.after(delay, tick_busy)
            except tk.TclError:
                return

        self._orbital_busy_after = self.after(BUSY_FRAME_MS, tick_busy)

    app_class._card = card
    app_class._tree = tree
    app_class.show_page = show_page
    app_class._build_shell = build_shell
    _INSTALLED_CLASSES.add(app_class)
