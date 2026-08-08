from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from all_flight_slots_fix import install_all_flight_slot_fix
from background_browser_fix import install_background_browser_fix
from bound_tab_fix import install_bound_tab_fix
from command_planet_exclusion import install_command_planet_exclusion
from farm_flight_classification_fix import install_farm_flight_classification_fix
from farm_no_target_retry import install_farm_no_target_retry
from farm_runtime_reliability import install_farm_capacity_fix, install_farm_ui_fix
from farm_wave_cooldown import install_farm_wave_cooldown
from fleet_capacity_presentation import install_fleet_capacity_presentation
from fleet_capacity_settings_fallback import install_fleet_capacity_settings_fallback
from flight_time_provenance_fix import install_flight_time_provenance_fix
from operational_variability import install_asteroid_scope_ui, install_raid_home_selection
from queue_row_numbering import install_queue_row_numbering
from raid_verification_fix import install_raid_verification_fix
from report_time_freshness_fix import install_report_time_freshness_fix
from resource_farm_auto import install_resource_farm_auto
from resource_queue_modes import install_resource_queue_modes
from ship_retry_fix import install_ship_retry_fix

install_bound_tab_fix()
install_ship_retry_fix()
install_raid_verification_fix()
install_background_browser_fix()

import app as app_module
from tk_layout_compat import install_tk_layout_compat
from visual_system import install_visual_system, prepare_visual_system
from visual_typography import install_typography
from visual_layout import install_debris_layout, install_visual_layout
from visual_tables import install_tables_dpi
from visual_motion import install_motion

# Classic Tk Frame options accept only scalar internal padding. The visual layout
# intentionally uses tuple-style spacing in a few places, so normalize it before
# any UI widgets are constructed.
install_tk_layout_compat()

# Install presentation primitives before feature modules import app-level UI symbols.
prepare_visual_system(app_module)

APP_NAME = app_module.APP_NAME
BaseRaidManagerApp = app_module.RaidManagerApp
make_button = app_module.make_button

import debris_asteroids_feature as debris_module
from page_capture import capture_current_page, default_snapshot_root

install_all_flight_slot_fix(BaseRaidManagerApp)
# 2:5:6 is the alliance/command planet, not part of this account's own fleet traffic.
# Filter every flight touching it before dashboards, slots, history, and auto modes read data.
install_command_planet_exclusion()
install_report_time_freshness_fix(BaseRaidManagerApp)
install_flight_time_provenance_fix()
install_raid_home_selection(app_module.BrowserWorker)

# Presentation and operational UI layers are installed before the app instance is built.
install_visual_system(app_module, BaseRaidManagerApp)
install_typography(BaseRaidManagerApp)
install_visual_layout(BaseRaidManagerApp)
install_resource_queue_modes(BaseRaidManagerApp)
install_asteroid_scope_ui(BaseRaidManagerApp)
install_tables_dpi(BaseRaidManagerApp)
install_queue_row_numbering(BaseRaidManagerApp)
install_resource_farm_auto(BaseRaidManagerApp)
# Empty fresh scans always wait exactly 25 minutes before the next scan.
install_farm_no_target_retry(BaseRaidManagerApp)
install_farm_flight_classification_fix(BaseRaidManagerApp)
# Capacity must wrap the classified send implementation before cooldown captures it.
install_farm_capacity_fix(app_module.BrowserWorker, BaseRaidManagerApp)
install_farm_wave_cooldown(BaseRaidManagerApp)
# UI repair runs after cooldown so the buffer variable/trace already exist.
install_farm_ui_fix(BaseRaidManagerApp)
# Sync/dashboard use the same live FleetsCount/MaxFleets values as the sender.
install_fleet_capacity_presentation(BaseRaidManagerApp)
# If Nemexia exposes a stale/zero max counter, fall back to the explicit app setting.
install_fleet_capacity_settings_fallback(app_module.BrowserWorker, BaseRaidManagerApp)
install_motion(BaseRaidManagerApp)
# Patch only debris presentation helpers before the feature wrapper captures the shell.
install_debris_layout(debris_module)
debris_module.install_debris_asteroid_feature(BaseRaidManagerApp)


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
            size="compact",
        )
        button.pack(side="right", padx=8, before=sync_button)

    def show_page(self, key: str) -> None:
        super().show_page(key)

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
