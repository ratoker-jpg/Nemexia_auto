from __future__ import annotations

import asyncio
from typing import Any

import tkinter as tk
from tkinter import messagebox

from app import APP_NAME, GREEN, MUTED, PANEL, PANEL_ALT, RED, TEXT, make_button
from browser import BrowserAutomationError, cdp_is_available
from proxy_auth_bridge import (
    AuthenticatedProxyBridge,
    check_http_proxy,
    launch_yandex_via_local_proxy,
)


_INSTALLED = False


def _entry(parent: tk.Misc, variable: tk.Variable, *, width: int = 28, secret: bool = False) -> tk.Entry:
    return tk.Entry(
        parent,
        textvariable=variable,
        width=width,
        bg=PANEL_ALT,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        show="•" if secret else "",
    )


def _config_from_values(
    enabled: bool,
    host: str,
    port_value: Any,
    username: str,
    password: str,
    *,
    require_enabled: bool = True,
) -> dict[str, Any]:
    if require_enabled and not enabled:
        raise BrowserAutomationError("Прокси выключен в настройках")
    host = str(host or "").strip()
    username = str(username or "")
    password = str(password or "")
    try:
        port = int(port_value)
    except Exception as exc:
        raise BrowserAutomationError("Некорректный порт прокси") from exc
    if not host:
        raise BrowserAutomationError("Укажи IP или хост HTTP-прокси")
    if port < 1 or port > 65535:
        raise BrowserAutomationError("Порт прокси должен быть в диапазоне 1–65535")
    if not username or not password:
        raise BrowserAutomationError("Укажи логин и пароль HTTP-прокси")
    return {
        "enabled": bool(enabled),
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


def _proxy_config(self: Any, *, require_enabled: bool = True) -> dict[str, Any]:
    return _config_from_values(
        bool(self.proxy_enabled_var.get()),
        self.proxy_host_var.get(),
        self.proxy_port_var.get(),
        self.proxy_username_var.get(),
        self.proxy_password_var.get(),
        require_enabled=require_enabled,
    )


def _persist_proxy_settings(self: Any) -> dict[str, Any]:
    enabled = bool(self.proxy_enabled_var.get())
    if enabled:
        config = _proxy_config(self, require_enabled=True)
    else:
        try:
            port = int(self.proxy_port_var.get())
        except Exception:
            port = 8000
        config = {
            "enabled": False,
            "host": str(self.proxy_host_var.get() or "").strip(),
            "port": port if 1 <= port <= 65535 else 8000,
            "username": str(self.proxy_username_var.get() or ""),
            "password": str(self.proxy_password_var.get() or ""),
        }
    values = {
        "proxy_enabled": bool(config["enabled"]),
        "proxy_type": "http",
        "proxy_host": config["host"],
        "proxy_port": int(config["port"]),
        "proxy_username": config["username"],
        "proxy_password": config["password"],
    }
    self.db.set_settings(values)
    self.settings.update(values)
    return config


def _stop_proxy_bridge(self: Any) -> None:
    bridge = getattr(self, "_proxy_bridge", None)
    if bridge is None:
        return
    try:
        bridge.stop()
    except Exception:
        pass
    self._proxy_bridge = None


def _open_proxy_dialog(self: Any) -> None:
    dialog = tk.Toplevel(self)
    dialog.title("Прокси браузера Nemexia")
    dialog.configure(bg=PANEL)
    dialog.resizable(False, False)
    dialog.transient(self)
    dialog.grab_set()

    enabled_var = tk.BooleanVar(value=bool(self.proxy_enabled_var.get()))
    host_var = tk.StringVar(value=str(self.proxy_host_var.get() or ""))
    port_var = tk.StringVar(value=str(self.proxy_port_var.get() or "8000"))
    username_var = tk.StringVar(value=str(self.proxy_username_var.get() or ""))
    password_var = tk.StringVar(value=str(self.proxy_password_var.get() or ""))
    status_var = tk.StringVar(value="Не проверен")

    body = tk.Frame(dialog, bg=PANEL, padx=22, pady=20)
    body.pack(fill="both", expand=True)
    tk.Checkbutton(
        body,
        text="Использовать HTTP-прокси для браузера Nemexia",
        variable=enabled_var,
        bg=PANEL,
        fg=TEXT,
        activebackground=PANEL,
        activeforeground=TEXT,
        selectcolor=PANEL_ALT,
        font=("Segoe UI Semibold", 9),
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

    fields = [
        ("IP / хост", host_var, False),
        ("Порт", port_var, False),
        ("Логин", username_var, False),
        ("Пароль", password_var, True),
    ]
    for row, (label, variable, secret) in enumerate(fields, start=1):
        tk.Label(body, text=label, bg=PANEL, fg=MUTED, anchor="w").grid(
            row=row, column=0, sticky="w", pady=7, padx=(0, 14)
        )
        _entry(body, variable, width=30, secret=secret).grid(row=row, column=1, sticky="w", pady=7, ipady=6)

    status_label = tk.Label(
        body,
        textvariable=status_var,
        bg=PANEL,
        fg=MUTED,
        anchor="w",
        font=("Segoe UI Semibold", 9),
        wraplength=360,
        justify="left",
    )
    status_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 6))

    note = (
        "Проверка открывает CONNECT к game.ares.nemexia.com:443 через указанный прокси. "
        "Если прокси включён и недоступен, браузер напрямую не запускается."
    )
    tk.Label(
        body,
        text=note,
        bg=PANEL,
        fg=MUTED,
        justify="left",
        wraplength=410,
        font=("Segoe UI", 8),
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 14))

    buttons = tk.Frame(body, bg=PANEL)
    buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(6, 0))

    def current_config() -> dict[str, Any]:
        return _config_from_values(
            bool(enabled_var.get()),
            host_var.get(),
            port_var.get(),
            username_var.get(),
            password_var.get(),
            require_enabled=False,
        )

    def run_test() -> None:
        try:
            config = current_config()
        except Exception as exc:
            status_var.set(str(exc))
            status_label.configure(fg=RED)
            return
        status_var.set("Проверка…")
        status_label.configure(fg=MUTED)

        async def operation() -> dict[str, Any]:
            return await asyncio.to_thread(
                check_http_proxy,
                config["host"],
                config["port"],
                config["username"],
                config["password"],
            )

        def success(_: dict[str, Any]) -> None:
            status_var.set("Прокси доступен · авторизация и CONNECT к Nemexia работают")
            status_label.configure(fg=GREEN)
            self.logger.info("Проверен HTTP-прокси %s:%s", config["host"], config["port"])

        def error(exc: Exception) -> None:
            status_var.set(str(exc))
            status_label.configure(fg=RED)
            self.logger.error("Проверка прокси не пройдена: %s", exc)

        self.run_task(operation(), "Проверка HTTP-прокси…", success, error, silent=True)

    def save() -> None:
        enabled = bool(enabled_var.get())
        if enabled:
            try:
                config = current_config()
            except Exception as exc:
                status_var.set(str(exc))
                status_label.configure(fg=RED)
                return
        else:
            try:
                port = int(port_var.get())
            except Exception:
                port = 8000
            config = {
                "enabled": False,
                "host": str(host_var.get() or "").strip(),
                "port": port if 1 <= port <= 65535 else 8000,
                "username": str(username_var.get() or ""),
                "password": str(password_var.get() or ""),
            }
        self.proxy_enabled_var.set(bool(config["enabled"]))
        self.proxy_host_var.set(config["host"])
        self.proxy_port_var.set(int(config["port"]))
        self.proxy_username_var.set(config["username"])
        self.proxy_password_var.set(config["password"])
        _persist_proxy_settings(self)
        if config["enabled"]:
            self.proxy_status_var.set(f"ВКЛ · {config['host']}:{config['port']}")
        else:
            self.proxy_status_var.set("ВЫКЛ")
        dialog.destroy()

    make_button(buttons, "Проверить", run_test, "secondary").pack(side="left", padx=5)
    make_button(buttons, "Отмена", dialog.destroy, "secondary").pack(side="left", padx=5)
    make_button(buttons, "Сохранить", save, "primary").pack(side="left", padx=5)
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.wait_visibility()
    dialog.focus_force()


def _launch_browser_with_proxy(self: Any, original_launch_browser) -> None:
    port = self._safe_int(self.port_var, 9222)
    if cdp_is_available(port):
        if bool(self.proxy_enabled_var.get()):
            messagebox.showinfo(
                APP_NAME,
                "Браузер уже запущен. Прокси нельзя изменить у работающего процесса.\n\n"
                "Закрой отдельный браузер Nemexia и снова нажми «Запустить браузер».",
            )
        else:
            self.status_var.set(f"Браузер уже запущен · порт {port}")
        return

    if not bool(self.proxy_enabled_var.get()):
        _persist_proxy_settings(self)
        _stop_proxy_bridge(self)
        original_launch_browser(self)
        return

    try:
        config = _persist_proxy_settings(self)
    except Exception as exc:
        messagebox.showerror(APP_NAME, str(exc))
        return

    self.proxy_status_var.set("Проверка перед запуском…")

    async def operation() -> dict[str, Any]:
        return await asyncio.to_thread(
            check_http_proxy,
            config["host"],
            config["port"],
            config["username"],
            config["password"],
        )

    def success(_: dict[str, Any]) -> None:
        _stop_proxy_bridge(self)
        bridge: AuthenticatedProxyBridge | None = None
        try:
            bridge = AuthenticatedProxyBridge(
                config["host"],
                config["port"],
                config["username"],
                config["password"],
            )
            local_port = bridge.start()
            self._proxy_bridge = bridge
            launch_yandex_via_local_proxy(port, local_port)
        except Exception as exc:
            if bridge is not None:
                try:
                    bridge.stop()
                except Exception:
                    pass
            self._proxy_bridge = None
            self.proxy_status_var.set(f"Ошибка запуска: {exc}")
            self.logger.error("Браузер через прокси не запущен: %s", exc)
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.proxy_status_var.set(f"ВКЛ · {config['host']}:{config['port']}")
        self.status_var.set("Яндекс Браузер запускается через прокси…")
        self.logger.info(
            "Запущен отдельный профиль Яндекс Браузера через HTTP-прокси %s:%s; локальный мост 127.0.0.1:%s",
            config["host"],
            config["port"],
            local_port,
        )
        self.after(1800, self.connect_browser)

    def error(exc: Exception) -> None:
        _stop_proxy_bridge(self)
        self.proxy_status_var.set(f"Прокси недоступен: {exc}")
        self.status_var.set("Прокси недоступен · браузер не запущен")
        self.logger.error("Прокси недоступен, прямой запуск запрещён: %s", exc)
        messagebox.showerror(
            APP_NAME,
            f"Прокси недоступен. Браузер Nemexia НЕ запущен напрямую.\n\n{exc}",
        )

    self.run_task(operation(), "Проверка прокси перед запуском…", success, error)


def install_authenticated_proxy_feature(app_class: type[Any]) -> None:
    """Add local authenticated HTTP proxy support without committing credentials."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_build_shell = app_class._build_shell
    original_build_settings_page = app_class._build_settings_page
    original_save_settings = app_class.save_settings
    original_save_settings_silent = app_class.save_settings_silent
    original_launch_browser = app_class.launch_browser
    original_exit_app = app_class.exit_app

    def build_shell(self: Any) -> None:
        self.proxy_enabled_var = tk.BooleanVar(value=bool(self.settings.get("proxy_enabled", False)))
        self.proxy_host_var = tk.StringVar(value=str(self.settings.get("proxy_host", "")))
        self.proxy_port_var = tk.IntVar(value=int(self.settings.get("proxy_port", 8000)))
        self.proxy_username_var = tk.StringVar(value=str(self.settings.get("proxy_username", "")))
        self.proxy_password_var = tk.StringVar(value=str(self.settings.get("proxy_password", "")))
        initial_proxy_status = (
            f"ВКЛ · {self.proxy_host_var.get()}:{self.proxy_port_var.get()}"
            if self.proxy_enabled_var.get()
            else "ВЫКЛ"
        )
        self.proxy_status_var = tk.StringVar(value=initial_proxy_status)
        self._proxy_bridge: AuthenticatedProxyBridge | None = None
        original_build_shell(self)

    def build_settings_page(self: Any) -> None:
        original_build_settings_page(self)
        page = self.pages.get("settings")
        if page is None:
            return
        form = None
        for panel in page.winfo_children():
            for child in panel.winfo_children():
                try:
                    columns, rows = child.grid_size()
                except Exception:
                    continue
                if columns >= 2 and rows >= 10:
                    form = child
                    break
            if form is not None:
                break
        if form is None:
            self.logger.warning("Не добавлены настройки прокси: форма настроек не найдена")
            return

        proxy_row = tk.Frame(form, bg=PANEL)
        tk.Label(
            proxy_row,
            textvariable=self.proxy_status_var,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=(0, 10))
        make_button(proxy_row, "Настроить прокси", lambda: _open_proxy_dialog(self), "secondary").pack(side="left")
        self._setting_row(
            form,
            14,
            "Прокси браузера",
            proxy_row,
            "HTTP с логином/паролем; при ошибке прямого fallback нет",
        )

    def save_settings(self: Any) -> None:
        try:
            _persist_proxy_settings(self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        original_save_settings(self)

    def save_settings_silent(self: Any) -> None:
        try:
            _persist_proxy_settings(self)
        except Exception:
            pass
        original_save_settings_silent(self)

    def launch_browser(self: Any) -> None:
        _launch_browser_with_proxy(self, original_launch_browser)

    def exit_app(self: Any) -> None:
        _stop_proxy_bridge(self)
        original_exit_app(self)

    app_class._build_shell = build_shell
    app_class._build_settings_page = build_settings_page
    app_class.save_settings = save_settings
    app_class.save_settings_silent = save_settings_silent
    app_class.launch_browser = launch_browser
    app_class.open_proxy_settings = lambda self: _open_proxy_dialog(self)
    app_class.exit_app = exit_app

    _INSTALLED = True
