from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from ship_retry_fix import install_ship_retry_fix

install_ship_retry_fix()

from app import APP_NAME, RaidManagerApp as BaseRaidManagerApp, make_button
from page_capture import capture_current_page, default_snapshot_root


SAVED_PAGES_DIR = default_snapshot_root()


class RaidManagerApp(BaseRaidManagerApp):
    """Application shell with an explicit manual browser-page snapshot action."""

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
