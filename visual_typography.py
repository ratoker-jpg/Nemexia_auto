from __future__ import annotations

from typing import Any
import tkinter.font as tkfont

from visual_system import (
    FONT_BODY,
    FONT_BODY_STRONG,
    FONT_CAPTION,
    FONT_DISPLAY,
    FONT_METRIC,
    FONT_MONO,
    FONT_PAGE_TITLE,
    FONT_SECTION_TITLE,
)


# Clean Windows desktop typography. The semantic font names stay stable so every
# existing widget keeps its role while the visual hierarchy becomes quieter.
TYPOGRAPHY = {
    FONT_DISPLAY: ("Segoe UI", 11, "bold"),
    FONT_PAGE_TITLE: ("Segoe UI", 18, "bold"),
    FONT_SECTION_TITLE: ("Segoe UI", 10, "bold"),
    FONT_METRIC: ("Segoe UI", 20, "bold"),
    FONT_BODY_STRONG: ("Segoe UI", 10, "bold"),
    FONT_BODY: ("Segoe UI", 10, "normal"),
    FONT_CAPTION: ("Segoe UI", 9, "normal"),
    FONT_MONO: ("Consolas", 9, "normal"),
}

_INSTALLED_CLASSES: set[type[Any]] = set()


def _apply_typography(root: Any) -> None:
    """Reconfigure existing named fonts without rebuilding or replacing widgets."""
    existing = set(tkfont.names(root))
    for name, (family, size, weight) in TYPOGRAPHY.items():
        if name in existing:
            font = tkfont.nametofont(name, root=root)
            font.configure(family=family, size=size, weight=weight)
        else:
            tkfont.Font(root=root, name=name, family=family, size=size, weight=weight)

    # Keep classic Tk widgets that do not specify a font aligned with the same
    # desktop baseline. Explicit semantic fonts above still take precedence.
    try:
        tkfont.nametofont("TkDefaultFont", root=root).configure(family="Segoe UI", size=10, weight="normal")
        tkfont.nametofont("TkTextFont", root=root).configure(family="Segoe UI", size=10, weight="normal")
        tkfont.nametofont("TkFixedFont", root=root).configure(family="Consolas", size=9, weight="normal")
    except Exception:
        # Some minimal Tk builds expose a smaller named-font set. Semantic fonts
        # above are sufficient, so missing platform defaults are non-fatal.
        pass


def install_typography(app_class: type[Any]) -> None:
    """Apply typography after the visual foundation creates its named fonts."""
    if app_class in _INSTALLED_CLASSES:
        return

    original_configure_style = app_class._configure_style

    def configure_style(self: Any) -> None:
        original_configure_style(self)
        _apply_typography(self)

    app_class._configure_style = configure_style
    _INSTALLED_CLASSES.add(app_class)
