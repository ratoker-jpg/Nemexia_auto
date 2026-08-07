from __future__ import annotations

from typing import Any

import tkinter as tk


_ORIGINAL_FRAME = tk.Frame
_INSTALLED = False


def normalize_classic_padding(value: Any) -> Any:
    """Return a scalar padding accepted by classic Tk widgets.

    Tk geometry managers accept two-value padding tuples, but classic widget
    options such as Frame(padx=..., pady=...) require a single screen distance.
    The visual layout used tuple-style internal padding in a few places, which
    Tcl serializes as e.g. ``"0 12"`` and rejects with ``bad screen distance``.

    For a tuple/list, keep the largest numeric distance. This preserves the
    intended amount of visual breathing room while converting it to Tk's
    supported symmetric internal padding.
    """
    if not isinstance(value, (tuple, list)):
        return value
    if not value:
        return 0

    numeric: list[float] = []
    for item in value:
        try:
            numeric.append(float(item))
        except (TypeError, ValueError):
            numeric = []
            break

    if numeric:
        chosen = max(numeric)
        return int(chosen) if chosen.is_integer() else chosen

    for item in reversed(value):
        if item not in (None, "", 0, "0"):
            return item
    return value[0]


class CompatibleFrame(_ORIGINAL_FRAME):
    """Classic Frame accepting tuple/list padx/pady without Tcl errors."""

    def __init__(
        self,
        master: tk.Misc | None = None,
        cnf: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        options = dict(cnf or {})
        options.update(kwargs)
        for key in ("padx", "pady"):
            if key in options:
                options[key] = normalize_classic_padding(options[key])
        super().__init__(master, options)


def install_tk_layout_compat() -> None:
    """Install the narrow Frame compatibility shim once for the UI bootstrap."""
    global _INSTALLED
    if _INSTALLED:
        return
    tk.Frame = CompatibleFrame
    _INSTALLED = True
