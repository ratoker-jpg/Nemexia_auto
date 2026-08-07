from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from all_flight_slots_fix import install_all_flight_slot_fix
from background_browser_fix import install_background_browser_fix
from bound_tab_fix import install_bound_tab_fix
from flight_time_provenance_fix import install_flight_time_provenance_fix
from raid_verification_fix import install_raid_verification_fix
from report_time_freshness_fix import install_report_time_freshness_fix
from ship_retry_fix import install_ship_retry_fix

install_bound_tab_fix()
install_ship_retry_fix()
install_raid_verification_fix()
install_background_browser_fix()

import app as app_module
from visual_system import install_visual_system, prepare_visual_system

# Install presentation primitives before feature modules import app-level UI symbols.
prepare_visual_system(app_module)

APP_NAME = app_module.APP_NAME
MUTED = app_module.MUTED
PANEL_ALT = app_module.PANEL_ALT
SIDEBAR = app_module.SIDEBAR
TEXT = app_module.TEXT
BaseRaidManagerApp = app_module.RaidManagerApp
make_button = app_module.make_button

from debris_asteroids_feature import install_debris_asteroid_feature
from page_capture import capture_current_page, default_snapshot_root

install_all_flight_slot_fix(BaseRaidManagerApp)
install_report_time_freshness_fix(BaseRaidManagerApp)
install_flight_time_provenance_fix()
install_debris_asteroid_feature(BaseRaidManagerApp)
# Install class-level visual helpers last so they wrap the complete production shell,
# including the debris feature, without changing any feature callbacks or data logic.
install_visual_system(app_module, BaseRaidManagerApp)


SAVED_PAGES_DIR = default_snapshot_root()


class RaidManagerApp(BaseRaidManagerApp):
    """Application shell with manual snapshots and the debris-asteroid page."""

    def _build_shell(self) -> None:
        super()._build_shell()
        sync_button = self._find_button("Синхронизировать")
        if sync_button is None:
            self.logger.warning("Не добавлена кнопка сохранения страницы: верхняя панель не найдена")
            return
        button = make_button(
            sync_button.master,
            "Сохранить страницу",
            self.save_current_page,
            "secondary",
        )
        button.pack(side="right", padx=8, before=sync_button)

    def show_page(self, key: str) -> None:
        if key != "debris":
            super().show_page(key)
            return
        self.current_page = key
        self.page_title_var.set("Астероиды с обломками")
        self.pages[key].tkraise()
        for nav_key, button in self.nav_buttons.items():
            button.configure(
                bg=PANEL_ALT if nav_key == key else SIDEBAR,
                fg=TEXT if nav_key == key else MUTED,
            )
        self.render_all()

    def _find_button(self, text: str) -> tk.Button | None:
        pending = list(self.winfo_children())
        while pending:
            widget = pending.pop(0)
            pending.extend(widget.winfo_children())
            if isinstance(widget, tk.Button) and str(widget.cget("text")) == text:
                return widget
        return None

    def save_current_page(self) -> None:
        endpoint = self.endpoint()

        async def operation() -> dict[str, str]:
            await self.worker.connect(endpoint)
            return await capture_current_page(self.worker, SAVED_PAGES_DIR, keep=10)

        def success(result: dict[str, str]) -> None:
            self.connected = True
            folder = Path(result["folder"])
            self.status_var.set("Страница сохранена")
            self.logger.info("Сохранена страница %s → %s", result.get("url") or "—", folder)
            warning = result.get("warnings") or ""
            suffix = f"\n\nЧасть форматов не сохранена:\n{warning}" if warning else ""
            messagebox.showinfo(
                APP_NAME,
                f"Текущая страница сохранена:\n{folder}\n\n"
                "Внутри: скриншот, HTML, MHTML и metadata.json.\n"
                "Хранятся 10 последних сохранений."
                + suffix,
            )

        def error(exc: Exception) -> None:
            self.logger.error("Не удалось сохранить текущую страницу: %s", exc)
            messagebox.showerror(APP_NAME, f"Не удалось сохранить страницу:\n{exc}")

        self.run_task(operation(), "Сохранение текущей страницы…", success, error)


def main() -> None:
    app = RaidManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
