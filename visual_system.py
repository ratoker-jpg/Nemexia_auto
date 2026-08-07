from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


# Orbital Command 2.0 — presentation-only design tokens.
SURFACE_0 = "#080d16"
SURFACE_1 = "#0b1220"
SURFACE_2 = "#101a2a"
SURFACE_3 = "#17243a"
BORDER_1 = "#24334a"
BORDER_FOCUS = "#4f8cff"
TEXT_1 = "#f1f6ff"
TEXT_2 = "#aab8ca"
TEXT_3 = "#74869c"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#78a7ff"
SUCCESS = "#4ed69a"
WARNING = "#ffc15a"
ERROR = "#ff7180"
INPUT_BG = "#0d1625"
SUCCESS_BG = "#102a24"
WARNING_BG = "#332713"
ERROR_BG = "#331820"
INFO_BG = "#10274a"
SELECTED_BG = "#193762"
LOG_BG = "#0a0f15"
LOG_TEXT = "#b8c5d5"

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32

FONT_DISPLAY = "Nemexia.Display"
FONT_PAGE_TITLE = "Nemexia.PageTitle"
FONT_SECTION_TITLE = "Nemexia.SectionTitle"
FONT_METRIC = "Nemexia.Metric"
FONT_BODY_STRONG = "Nemexia.BodyStrong"
FONT_BODY = "Nemexia.Body"
FONT_CAPTION = "Nemexia.Caption"
FONT_MONO = "Nemexia.Mono"


@dataclass(frozen=True)
class ButtonSpec:
    background: str
    foreground: str
    hover: str
    pressed: str


BUTTON_SPECS = {
    "primary": ButtonSpec(ACCENT, TEXT_1, ACCENT_HOVER, "#3d73d7"),
    "warning": ButtonSpec(WARNING, "#241800", "#ffd17a", "#d9a23f"),
    "success": ButtonSpec(SUCCESS, "#06150e", "#65dfa5", "#35b87d"),
    "danger": ButtonSpec(ERROR, "#220509", "#ff8790", "#db5564"),
    "secondary": ButtonSpec(SURFACE_3, TEXT_1, "#21324e", BORDER_1),
    "ghost": ButtonSpec(SURFACE_2, TEXT_2, SURFACE_3, "#0d1625"),
}

BUTTON_SIZES = {
    "regular": {"padx": 14, "pady": 8},
    "compact": {"padx": 11, "pady": 5},
}

_LEFT_COLUMNS = {
    "player",
    "notes",
    "error",
    "status",
    "state",
}
_RIGHT_COLUMNS = {
    "energy",
    "metal",
    "minerals",
    "resource_gas",
    "gas",
    "total",
    "score",
    "loot",
    "population",
    "ships",
    "defense",
    "count",
    "shifts",
}
_CENTER_COLUMNS = {
    "coord",
    "target",
    "origin",
    "picked",
    "position",
    "flag",
    "fleet",
    "date",
    "sent",
    "arrival",
    "return",
    "arrival_at",
    "arrival_left",
    "return_at",
    "return_left",
    "spy_at",
    "snapshot",
    "last",
    "returned",
    "scanned",
    "next",
    "period",
    "one",
    "round",
    "trip",
    "age",
}

_TK_ENTRY = tk.Entry
_TK_SPINBOX = tk.Spinbox
_TK_CHECKBUTTON = tk.Checkbutton
_PREPARED = False
_INSTALLED_CLASSES: set[type[Any]] = set()


def tree_column_anchor(column: str) -> str:
    key = str(column).casefold()
    if key in _LEFT_COLUMNS:
        return "w"
    if key in _RIGHT_COLUMNS:
        return "e"
    if key in _CENTER_COLUMNS:
        return "center"
    return "center"


def _parent_background(parent: tk.Misc, fallback: str = SURFACE_2) -> str:
    try:
        value = str(parent.cget("bg"))
        return value or fallback
    except Exception:
        return fallback


class OrbitalEntry(_TK_ENTRY):
    def __init__(self, master: tk.Misc | None = None, cnf: dict[str, Any] | None = None, **kwargs: Any) -> None:
        kwargs.update(
            bg=INPUT_BG,
            fg=TEXT_1,
            insertbackground=TEXT_1,
            disabledbackground=SURFACE_2,
            disabledforeground=TEXT_3,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_1,
            highlightcolor=BORDER_FOCUS,
            font=FONT_BODY,
            takefocus=True,
        )
        super().__init__(master, cnf or {}, **kwargs)


class OrbitalSpinbox(_TK_SPINBOX):
    def __init__(self, master: tk.Misc | None = None, cnf: dict[str, Any] | None = None, **kwargs: Any) -> None:
        kwargs.update(
            bg=INPUT_BG,
            fg=TEXT_1,
            insertbackground=TEXT_1,
            buttonbackground=SURFACE_3,
            disabledbackground=SURFACE_2,
            disabledforeground=TEXT_3,
            readonlybackground=INPUT_BG,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_1,
            highlightcolor=BORDER_FOCUS,
            font=FONT_BODY,
            takefocus=True,
        )
        super().__init__(master, cnf or {}, **kwargs)


class OrbitalCheckbutton(_TK_CHECKBUTTON):
    def __init__(self, master: tk.Misc | None = None, cnf: dict[str, Any] | None = None, **kwargs: Any) -> None:
        parent_bg = _parent_background(master, SURFACE_2) if master is not None else SURFACE_2
        kwargs.update(
            bg=parent_bg,
            fg=TEXT_1,
            activebackground=parent_bg,
            activeforeground=TEXT_1,
            disabledforeground=TEXT_3,
            selectcolor=SURFACE_3,
            highlightthickness=1,
            highlightbackground=parent_bg,
            highlightcolor=BORDER_FOCUS,
            font=FONT_BODY,
            takefocus=True,
        )
        super().__init__(master, cnf or {}, **kwargs)


def _ensure_named_fonts(root: tk.Misc) -> None:
    definitions = {
        FONT_DISPLAY: ("Segoe UI", 24, "bold"),
        FONT_PAGE_TITLE: ("Segoe UI", 20, "bold"),
        FONT_SECTION_TITLE: ("Segoe UI", 12, "bold"),
        FONT_METRIC: ("Segoe UI", 24, "bold"),
        FONT_BODY_STRONG: ("Segoe UI", 9, "bold"),
        FONT_BODY: ("Segoe UI", 9, "normal"),
        FONT_CAPTION: ("Segoe UI", 8, "normal"),
        FONT_MONO: ("Consolas", 9, "normal"),
    }
    existing = set(tkfont.names(root))
    for name, (family, size, weight) in definitions.items():
        if name in existing:
            font = tkfont.nametofont(name, root=root)
            font.configure(family=family, size=size, weight=weight)
        else:
            tkfont.Font(root=root, name=name, family=family, size=size, weight=weight)


def _button_spec(kind: str) -> ButtonSpec:
    return BUTTON_SPECS.get(kind, BUTTON_SPECS["secondary"])


def make_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    kind: str = "secondary",
    width: int | None = None,
    *,
    size: str = "regular",
) -> tk.Button:
    spec = _button_spec(kind)
    metrics = BUTTON_SIZES.get(size, BUTTON_SIZES["regular"])
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=spec.background,
        fg=spec.foreground,
        activebackground=spec.pressed,
        activeforeground=spec.foreground,
        disabledforeground=TEXT_3,
        relief="flat",
        bd=0,
        padx=metrics["padx"],
        pady=metrics["pady"],
        cursor="hand2",
        highlightthickness=2,
        highlightbackground=spec.background,
        highlightcolor=BORDER_FOCUS,
        font=FONT_BODY_STRONG,
        takefocus=True,
        width=width,
    )

    def on_enter(_: tk.Event) -> None:
        if str(button.cget("state")) != "disabled":
            button.configure(bg=spec.hover, highlightbackground=spec.hover)

    def on_leave(_: tk.Event) -> None:
        if str(button.cget("state")) != "disabled":
            button.configure(bg=spec.background, highlightbackground=spec.background)

    def on_focus(_: tk.Event) -> None:
        button.configure(highlightbackground=BORDER_FOCUS)

    def on_blur(_: tk.Event) -> None:
        if str(button.cget("state")) != "disabled":
            button.configure(highlightbackground=button.cget("bg"))

    button.bind("<Enter>", on_enter, add="+")
    button.bind("<Leave>", on_leave, add="+")
    button.bind("<FocusIn>", on_focus, add="+")
    button.bind("<FocusOut>", on_blur, add="+")
    return button


def make_entry(parent: tk.Misc, variable: tk.Variable | None = None, *, width: int | None = None, **kwargs: Any) -> tk.Entry:
    if variable is not None:
        kwargs["textvariable"] = variable
    if width is not None:
        kwargs["width"] = width
    return OrbitalEntry(parent, **kwargs)


def make_spinbox(
    parent: tk.Misc,
    variable: tk.Variable,
    *,
    from_: int,
    to: int,
    width: int = 8,
    **kwargs: Any,
) -> tk.Spinbox:
    return OrbitalSpinbox(parent, from_=from_, to=to, textvariable=variable, width=width, **kwargs)


def make_check(
    parent: tk.Misc,
    variable: tk.BooleanVar,
    text: str,
    command: Callable[[], None] | None = None,
    **kwargs: Any,
) -> tk.Checkbutton:
    return OrbitalCheckbutton(parent, text=text, variable=variable, command=command, **kwargs)


def make_field_label(parent: tk.Misc, text: str, **kwargs: Any) -> tk.Label:
    return tk.Label(parent, text=text, bg=_parent_background(parent), fg=TEXT_2, font=FONT_CAPTION, anchor="w", **kwargs)


def make_helper_text(parent: tk.Misc, text: str = "", *, textvariable: tk.Variable | None = None, **kwargs: Any) -> tk.Label:
    options: dict[str, Any] = {
        "bg": _parent_background(parent),
        "fg": TEXT_3,
        "font": FONT_CAPTION,
        "anchor": "w",
    }
    options.update(kwargs)
    if textvariable is not None:
        options["textvariable"] = textvariable
    else:
        options["text"] = text
    return tk.Label(parent, **options)


def prepare_visual_system(app_module: Any) -> None:
    """Install token and widget primitives before feature modules import app symbols."""
    global _PREPARED
    if _PREPARED:
        return

    token_mapping = {
        "BG": SURFACE_0,
        "SIDEBAR": SURFACE_1,
        "PANEL": SURFACE_2,
        "PANEL_ALT": SURFACE_3,
        "BORDER": BORDER_1,
        "TEXT": TEXT_1,
        "MUTED": TEXT_2,
        "ACCENT": ACCENT,
        "ACCENT_HOVER": ACCENT_HOVER,
        "GREEN": SUCCESS,
        "YELLOW": WARNING,
        "RED": ERROR,
        "BLUE_DARK": SELECTED_BG,
        "INPUT": INPUT_BG,
        "CARD_GLOW": INFO_BG,
    }
    for name, value in token_mapping.items():
        setattr(app_module, name, value)

    # These replacements preserve the Tk widget API and callbacks while making all
    # current Entry/Spinbox/Checkbutton call sites share the same presentation.
    tk.Entry = OrbitalEntry
    tk.Spinbox = OrbitalSpinbox
    tk.Checkbutton = OrbitalCheckbutton
    app_module.make_button = make_button
    _PREPARED = True


def install_visual_system(app_module: Any, app_class: type[Any]) -> None:
    """Install presentation-only helpers on the production app class."""
    if app_class in _INSTALLED_CLASSES:
        return

    def configure_style(self: Any) -> None:
        _ensure_named_fonts(self)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Dark.Treeview",
            background=SURFACE_2,
            fieldbackground=SURFACE_2,
            foreground=TEXT_1,
            rowheight=38,
            borderwidth=0,
            font=FONT_BODY,
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", SELECTED_BG), ("!selected", SURFACE_2)],
            foreground=[("selected", TEXT_1)],
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=SURFACE_3,
            foreground=TEXT_2,
            relief="flat",
            font=FONT_BODY_STRONG,
            padding=(SPACE_MD, SPACE_MD),
        )
        style.map(
            "Dark.Treeview.Heading",
            background=[("active", INFO_BG)],
            foreground=[("active", TEXT_1)],
        )
        style.configure("Dark.TNotebook", background=SURFACE_0, borderwidth=0)
        style.configure(
            "Dark.TNotebook.Tab",
            background=SURFACE_2,
            foreground=TEXT_2,
            padding=(SPACE_LG, SPACE_SM),
            font=FONT_BODY_STRONG,
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", SURFACE_3)],
            foreground=[("selected", TEXT_1)],
        )
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=INPUT_BG, foreground=TEXT_1)
        style.configure("TSpinbox", fieldbackground=INPUT_BG, background=INPUT_BG, foreground=TEXT_1)
        style.configure(
            "Vertical.TScrollbar",
            background=SURFACE_3,
            troughcolor=SURFACE_0,
            bordercolor=SURFACE_0,
            arrowsize=13,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=SURFACE_3,
            troughcolor=SURFACE_0,
            bordercolor=SURFACE_0,
            arrowsize=13,
        )

    def tree(
        self: Any,
        parent: tk.Misc,
        columns: tuple[str, ...],
        headings: dict[str, str],
        widths: dict[str, int],
        selectmode: str = "browse",
    ) -> tuple[ttk.Treeview, ttk.Scrollbar]:
        view = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            style="Dark.Treeview",
            selectmode=selectmode,
        )
        for column in columns:
            anchor = tree_column_anchor(column)
            view.heading(
                column,
                text=headings.get(column, column),
                anchor=anchor,
                command=lambda col=column, widget=view: self._sort_tree(widget, col),
            )
            view.column(
                column,
                width=widths.get(column, 100),
                minwidth=45,
                anchor=anchor,
            )
        scroll = ttk.Scrollbar(parent, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        return view, scroll

    def section(self: Any, parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        panel = tk.Frame(parent, bg=SURFACE_2, highlightbackground=BORDER_1, highlightthickness=1)
        header = tk.Frame(panel, bg=SURFACE_2, padx=SPACE_LG, pady=SPACE_MD)
        header.pack(fill="x")
        tk.Label(header, text=title, bg=SURFACE_2, fg=TEXT_1, font=FONT_SECTION_TITLE).pack(side="left")
        if subtitle:
            tk.Label(header, text=subtitle, bg=SURFACE_2, fg=TEXT_2, font=FONT_BODY).pack(
                side="left", padx=(SPACE_MD, 0)
            )
        return panel

    def card(self: Any, parent: tk.Misc, title: str, variable: tk.StringVar, subtitle: str) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=SURFACE_2,
            highlightbackground=BORDER_1,
            highlightthickness=1,
            padx=SPACE_LG,
            pady=SPACE_LG,
        )
        tk.Label(frame, text=title, bg=SURFACE_2, fg=TEXT_2, font=FONT_BODY_STRONG).pack(anchor="w")
        tk.Label(frame, textvariable=variable, bg=SURFACE_2, fg=TEXT_1, font=FONT_METRIC).pack(
            anchor="w", pady=(SPACE_SM, SPACE_XS)
        )
        tk.Label(frame, text=subtitle, bg=SURFACE_2, fg=TEXT_3, font=FONT_CAPTION).pack(anchor="w")
        return frame

    original_build_shell = app_class._build_shell

    def build_shell(self: Any) -> None:
        original_build_shell(self)
        semantic_tags = (
            ("queue_tree", {"active": SUCCESS_BG, "sending": INFO_BG, "failed": ERROR_BG}),
            ("asteroid_tree", {"ready": SUCCESS_BG, "error": ERROR_BG}),
            ("targets_tree", {"active": SUCCESS_BG}),
            ("debris_tree", {"sent": SUCCESS_BG, "error": ERROR_BG}),
        )
        for attr, tags in semantic_tags:
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            for tag, background in tags.items():
                widget.tag_configure(tag, background=background)
        if hasattr(self, "queue_tree"):
            self.queue_tree.tag_configure("sent", foreground=TEXT_3)
        if hasattr(self, "asteroid_tree"):
            self.asteroid_tree.tag_configure("sent", foreground=SUCCESS)
        if hasattr(self, "targets_tree"):
            self.targets_tree.tag_configure("black", foreground=TEXT_3)
            self.targets_tree.tag_configure("disabled", foreground=TEXT_3)
        if hasattr(self, "log_text"):
            self.log_text.configure(bg=LOG_BG, fg=LOG_TEXT, insertbackground=TEXT_1, font=FONT_MONO)

    app_class._configure_style = configure_style
    app_class._tree = tree
    app_class._section = section
    app_class._card = card
    app_class._build_shell = build_shell
    app_class.make_entry = staticmethod(make_entry)
    app_class.make_spinbox = staticmethod(make_spinbox)
    app_class.make_check = staticmethod(make_check)
    app_class.make_field_label = staticmethod(make_field_label)
    app_class.make_helper_text = staticmethod(make_helper_text)

    # Expose presentation helpers for feature modules without changing feature logic.
    app_module.make_entry = make_entry
    app_module.make_spinbox = make_spinbox
    app_module.make_check = make_check
    app_module.make_field_label = make_field_label
    app_module.make_helper_text = make_helper_text

    _INSTALLED_CLASSES.add(app_class)
