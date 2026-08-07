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


def _proxy_config(self: Any, *, require_enabled: bool = True) -> dict[str, Any]:
    enabled = bool(self.proxy_enabled_var.get())
    if require_enabled and not enabled:
        raise BrowserAutomationError("Прокси выключен в настройках")
    host = str(self.proxy_host_var.get() or "").strip()
    username = str(self.proxy_username_var.get() or "")
    password = str(self.proxy_password_var.get() or "")
    try:
        port = int(self.proxy_port_var.get())
    except Exception as exc:
        raise BrowserAutomationError("Некорректный порт прокси") from exc
    if not host:
        raise BrowserAutomationError("Укажи IP или хост HTTP-прокси")
    if port < 1 or port > 65535:
        raise BrowserAutomationError("Порт прокси должен быть в диапазоне 1–65535")
    if not username or not password:
        raise BrowserAutomationError("Укажи логин и пароль HTTP-прокси")
    return {
        "enabled": enabled,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


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


def _test_proxy(self: Any) -> None:
    try:
        config = _proxy_config(self, require_enabled=False)
    except Exception as exc:
        messagebox.showerror(APP_NAME, str(exc))
        return

    self.proxy_status_var.set("Проверка…")

    async def operation() -> dict[str, Any]:
        return await asyncio.to_thread(
            check_http_proxy,
            config["host"],
            config["port"],
            config["username"],
            config["password"],
        )

    def success(_: dict[str, Any]) -> None:
        self.proxy_status_var.set("Прокси доступен · Nemexia открывается")
        if hasattr(self, "proxy_status_label"):
            self.proxy_status_label.configure(fg=GREEN)
        self.logger.info("Проверен HTTP-прокси %s:%s", config["host"], config["port"])
        messagebox.showinfo(APP_NAME, "Прокси доступен. Авторизация прошла, соединение с Nemexia открывается.")

    def error(exc: Exception) -> None:
        self.proxy_status_var.set(f"Ошибка: {exc}")
        if hasattr(self, "proxy_status_label"):
            self.proxy_status_label.configure(fg=RED)
        self.logger.error("Проверка прокси не пройдена: %s", exc)
        messagebox.showerror(APP_NAME, str(exc))

    self.run_task(operation(), "Проверка HTTP-прокси…", success, error)


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
            if hasattr(self, "proxy_status_label"):
                self.proxy_status_label.configure(fg=RED)
            self.logger.error("Браузер через прокси не запущен: %s", exc)
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.proxy_status_var.set(f"ВКЛ · {config['host']}:{config['port']}")
        if hasattr(self, "proxy_status_label"):
            self.proxy_status_label.configure(fg=GREEN)
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
        if hasattr(self, "proxy_status_label"):
            self.proxy_status_label.configure(fg=RED)
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
    original_launch_browser = app_class.launch_browser
    original_on_close = app_class.on_close

    def build_shell(self: Any) -> None:
        self.proxy_enabled_var = tk.BooleanVar(value=bool(self.settings.get("proxy_enabled", False)))
        self.proxy_host_var = tk.StringVar(value=str(self.settings.get("proxy_host", "")))
        self.proxy_port_var = tk.IntVar(value=int(self.settings.get("proxy_port", 8000)))
        self.proxy_username_var = tk.StringVar(value=str(self.settings.get("proxy_username", "")))
        self.proxy_password_var = tk.StringVar(value=str(self.settings.get("proxy_password", "")))
        self.proxy_status_var = tk.StringVar(value="Не проверен")
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

        enabled = tk.Checkbutton(
            form,
            text="Использовать HTTP-прокси для браузера Nemexia",
            variable=self.proxy_enabled_var,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=PANEL_ALT,
        )
        self._setting_row(
            form,
            14,
            "Прокси браузера",
            enabled,
            "при ошибке прямое соединение не используется",
        )
        self._setting_row(form, 15, "IP / хост", _entry(form, self.proxy_host_var), "например 163.198.215.160")
        proxy_port = tk.Spinbox(
            form,
            from_=1,
            to=65535,
            textvariable=self.proxy_port_var,
            width=8,
            bg=PANEL_ALT,
            fg=TEXT,
            buttonbackground=PANEL_ALT,
            insertbackground=TEXT,
            relief="flat",
        )
        self._setting_row(form, 16, "Порт прокси", proxy_port, "HTTP")
        self._setting_row(form, 17, "Логин прокси", _entry(form, self.proxy_username_var), "хранится только в локальной базе")
        self._setting_row(
            form,
            18,
            "Пароль прокси",
            _entry(form, self.proxy_password_var, secret=True),
            "не записывается в GitHub; сохраняется локально",
        )

        status_frame = tk.Frame(form, bg=PANEL)
        self.proxy_status_label = tk.Label(
            status_frame,
            textvariable=self.proxy_status_var,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
        )
        self.proxy_status_label.pack(side="left", padx=(0, 10))
        make_button(status_frame, "Проверить прокси", lambda: _test_proxy(self), "secondary").pack(side="left")
        self._setting_row(form, 19, "Статус прокси", status_frame, "проверяется доступ к game.ares.nemexia.com:443")

    def save_settings(self: Any) -> None:
        try:
            _persist_proxy_settings(self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        original_save_settings(self)

    def launch_browser(self: Any) -> None:
        _launch_browser_with_proxy(self, original_launch_browser)

    def on_close(self: Any) -> None:
        _stop_proxy_bridge(self)
        original_on_close(self)

    app_class._build_shell = build_shell
    app_class._build_settings_page = build_settings_page
    app_class.save_settings = save_settings
    app_class.launch_browser = launch_browser
    app_class.test_proxy_connection = lambda self: _test_proxy(self)
    app_class.on_close = on_close

    _INSTALLED = True
