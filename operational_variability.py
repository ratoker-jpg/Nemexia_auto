from __future__ import annotations

from typing import Any

import tkinter as tk

from config import FLEETS_URL
from visual_system import SPACE_LG, SPACE_SM


_PATCHED_WORKERS: set[type[Any]] = set()
_PATCHED_APPS: set[type[Any]] = set()


def install_raid_home_selection(worker_class: type[Any]) -> None:
    """Select the configured raid home before preparing normal attack ships."""
    if worker_class in _PATCHED_WORKERS:
        return

    original_prepare_fleet = worker_class._prepare_fleet

    async def prepare_fleet(
        self: Any,
        page: Any,
        ship_count: int,
        home: tuple[int, int, int],
    ) -> str:
        # Asteroid/recycler flows already use _select_planet(). Reuse the same
        # proven planet switch for normal raids before any ship state is entered.
        await self._assert_no_captcha(page, "captcha_before_raid_planet_switch")
        await self._select_planet(page, home)
        if "fleets.php" not in page.url:
            await page.goto(FLEETS_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.locator("#mainFrame").wait_for(state="attached", timeout=15_000)
        await self._assert_no_captcha(page, "captcha_raid_home_ready")
        return await original_prepare_fleet(self, page, ship_count, home)

    worker_class._prepare_fleet = prepare_fleet
    _PATCHED_WORKERS.add(worker_class)


def _find_label(root: tk.Misc, text: str) -> tk.Label | None:
    pending = list(root.winfo_children())
    while pending:
        widget = pending.pop(0)
        pending.extend(widget.winfo_children())
        if isinstance(widget, tk.Label):
            try:
                if str(widget.cget("text")) == text:
                    return widget
            except Exception:
                continue
    return None


def install_asteroid_scope_ui(app_class: type[Any]) -> None:
    """Expose the already-supported asteroid galaxy setting in the visual layout."""
    if app_class in _PATCHED_APPS:
        return

    original_build_asteroids_page = app_class._build_asteroids_page

    def build_asteroids_page(self: Any) -> None:
        original_build_asteroids_page(self)
        page = self.pages.get("asteroids")
        if page is None:
            return

        start_label = _find_label(page, "Система от")
        if start_label is None:
            return
        start_block = start_label.master
        range_row = start_block.master
        if getattr(range_row, "_asteroid_galaxy_control", False):
            return

        bg = str(range_row.cget("bg"))
        galaxy_block = tk.Frame(range_row, bg=bg)
        self.make_field_label(galaxy_block, "Галактика").pack(anchor="w")
        self.make_spinbox(
            galaxy_block,
            self.asteroid_galaxy_var,
            from_=1,
            to=3,
            width=4,
        ).pack(anchor="w", pady=(SPACE_SM, 0), ipady=4)
        galaxy_block.pack(side="left", padx=(0, SPACE_LG), before=start_block)
        setattr(range_row, "_asteroid_galaxy_control", True)

        home_label = _find_label(page, "Исходная планета")
        if home_label is not None:
            home_label.configure(text="Исходная планета добычи")

    app_class._build_asteroids_page = build_asteroids_page
    _PATCHED_APPS.add(app_class)
