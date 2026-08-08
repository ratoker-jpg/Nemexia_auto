from __future__ import annotations

import time
from typing import Any

import tkinter as tk


NO_TARGET_RETRY_MINUTES = 25
_INSTALLED_CLASSES: set[type[Any]] = set()


def _walk(root: tk.Misc) -> list[tk.Misc]:
    result: list[tk.Misc] = []
    pending = list(root.winfo_children())
    while pending:
        widget = pending.pop(0)
        result.append(widget)
        try:
            pending.extend(widget.winfo_children())
        except Exception:
            pass
    return result


def _replace_text(root: tk.Misc, old: str, new: str) -> None:
    for widget in _walk(root):
        try:
            if str(widget.cget("text")) == old:
                widget.configure(text=new)
        except Exception:
            pass


def install_farm_no_target_retry(app_class: type[Any]) -> None:
    """Force a fixed 25-minute pause after a fresh scan yields zero 500k targets.

    resource_farm_auto historically reused repeat_minutes_var for this branch.
    That setting may contain an older persisted value (for example 60 minutes).
    This layer keeps the rest of the cycle untouched and normalizes only the
    no-target cooldown/status after the scan result is known.
    """
    if app_class in _INSTALLED_CLASSES:
        return

    original_set_status = app_class._set_farm_status
    original_build_settings_page = app_class._build_settings_page

    def set_status(self: Any, text: str, *, topbar: bool = True) -> None:
        prefix = "Автофарм · целей с 500 000 минералов нет"
        if str(text).startswith(prefix):
            self._farm_idle_until = time.monotonic() + NO_TARGET_RETRY_MINUTES * 60
            text = f"{prefix} · повтор через {NO_TARGET_RETRY_MINUTES} мин"
            try:
                self.logger.info(
                    "Автофарм: после пустой разведки пауза %s минут",
                    NO_TARGET_RETRY_MINUTES,
                )
            except Exception:
                pass
        original_set_status(self, text, topbar=topbar)

    def build_settings_page(self: Any) -> None:
        original_build_settings_page(self)
        page = self.pages.get("settings")
        if page is None:
            return
        _replace_text(
            page,
            "Повтор без подходящих целей",
            "Повторный рейд (старый параметр)",
        )
        _replace_text(
            page,
            "минут до следующей разведки, если целей с 500 000 минералов нет",
            "автофарм 500k: при 0 подходящих целей пауза всегда 25 минут",
        )

    app_class._set_farm_status = set_status
    app_class._build_settings_page = build_settings_page
    _INSTALLED_CLASSES.add(app_class)
