from __future__ import annotations

import asyncio
import csv
import logging
import logging.handlers
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from browser import (
    BrowserAutomationError,
    BrowserWorker,
    CaptchaRequiredError,
    cdp_is_available,
    launch_yandex,
)
from config import (
    APP_NAME,
    APP_VERSION,
    BACKUP_DIR,
    DATA_DIR,
    DB_PATH,
    ICON_PATH,
    LOG_DIR,
    RESOURCE_DIR,
    SEED_PATH,
)
from models import AsteroidObservation, AsteroidPlan, Flight, QueueItem, SpyReport, Target, parse_dt, utc_now
from reports import parse_report_paths
from storage import Database, is_protected_coord
from ui_utils import format_clock, format_datetime, format_duration, format_number, remaining

try:
    import pystray
    from PIL import Image
except Exception:  # pragma: no cover - optional tray fallback
    pystray = None
    Image = None


BG = "#080d16"
SIDEBAR = "#0b1220"
PANEL = "#101a2a"
PANEL_ALT = "#17243a"
BORDER = "#24334a"
TEXT = "#f1f6ff"
MUTED = "#93a4ba"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#78a7ff"
GREEN = "#4ed69a"
YELLOW = "#ffc15a"
RED = "#ff7180"
BLUE_DARK = "#193762"
INPUT = "#0d1625"
CARD_GLOW = "#1d2f4a"


class MemoryLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.callback(self.format(record))
        except Exception:
            pass


def setup_logging(callback: Callable[[str], None]) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("nemexia")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%d.%m.%Y %H:%M:%S")
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "nemexia.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    memory = MemoryLogHandler(callback)
    memory.setFormatter(formatter)
    logger.addHandler(memory)
    return logger


class TrayController:
    def __init__(self, app: "RaidManagerApp") -> None:
        self.app = app
        self.icon = None
        self.thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return pystray is not None and Image is not None and ICON_PATH.exists()

    def start(self) -> None:
        if not self.available or self.icon is not None:
            return
        image = Image.open(ICON_PATH)
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda *_: self.app.after(0, self.app.restore_from_tray)),
            pystray.MenuItem("Синхронизировать", lambda *_: self.app.after(0, self.app.sync_flights)),
            pystray.MenuItem("Выход", lambda *_: self.app.after(0, self.app.exit_app)),
        )
        self.icon = pystray.Icon("NemexiaRaidManager", image, APP_NAME, menu)
        self.thread = threading.Thread(target=self.icon.run, daemon=True, name="tray")
        self.thread.start()

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
        self.icon = None

    def notify(self, title: str, message: str) -> None:
        if self.icon:
            try:
                self.icon.notify(message, title)
                return
            except Exception:
                pass
        try:
            if os.name == "nt":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass


class TargetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, target: Target | None = None) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.title("Цель")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.coord_var = tk.StringVar(value=target.coord if target else "")
        self.player_var = tk.StringVar(value=target.player if target else "")
        self.energy_var = tk.StringVar(value=str(target.energy if target else 7000))
        self.notes_var = tk.StringVar(value=target.notes if target else "")
        self.enabled_var = tk.BooleanVar(value=target.enabled if target else True)
        self.black_var = tk.BooleanVar(value=target.blacklisted if target else False)

        frame = tk.Frame(self, bg=PANEL, padx=20, pady=18)
        frame.pack(fill="both", expand=True)
        fields = [
            ("Координаты G:S:P", self.coord_var),
            ("Игрок", self.player_var),
            ("Энергия", self.energy_var),
            ("Заметка", self.notes_var),
        ]
        for row, (label, var) in enumerate(fields):
            tk.Label(frame, text=label, bg=PANEL, fg=MUTED, anchor="w").grid(row=row, column=0, sticky="w", pady=6)
            entry = tk.Entry(frame, textvariable=var, bg=PANEL_ALT, fg=TEXT, insertbackground=TEXT,
                             relief="flat", width=34, font=("Segoe UI", 10))
            entry.grid(row=row, column=1, padx=(14, 0), pady=6, ipady=6)
        tk.Checkbutton(frame, text="Активна", variable=self.enabled_var, bg=PANEL, fg=TEXT,
                       activebackground=PANEL, activeforeground=TEXT, selectcolor=PANEL_ALT).grid(
            row=4, column=0, sticky="w", pady=(10, 4)
        )
        tk.Checkbutton(frame, text="Чёрный список", variable=self.black_var, bg=PANEL, fg=TEXT,
                       activebackground=PANEL, activeforeground=TEXT, selectcolor=PANEL_ALT).grid(
            row=4, column=1, sticky="w", pady=(10, 4)
        )
        buttons = tk.Frame(frame, bg=PANEL)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(18, 0))
        make_button(buttons, "Отмена", self.destroy, "secondary").pack(side="left", padx=5)
        make_button(buttons, "Сохранить", self._save, "primary").pack(side="left", padx=5)
        self.bind("<Return>", lambda _: self._save())
        self.bind("<Escape>", lambda _: self.destroy())
        self.wait_visibility()
        self.focus_force()

    def _save(self) -> None:
        coord = self.coord_var.get().strip().replace("-", ":")
        parts = coord.split(":")
        try:
            if len(parts) != 3:
                raise ValueError
            g, s, p = (int(x) for x in parts)
            if min(g, s, p) <= 0:
                raise ValueError
            energy = int(self.energy_var.get().replace(" ", ""))
        except ValueError:
            messagebox.showerror(APP_NAME, "Проверь координаты и энергию", parent=self)
            return
        self.result = {
            "coord": f"{g}:{s}:{p}", "player": self.player_var.get().strip() or "—",
            "energy": energy, "notes": self.notes_var.get().strip(),
            "enabled": self.enabled_var.get(), "blacklisted": self.black_var.get(),
        }
        self.destroy()


def make_button(parent: tk.Misc, text: str, command: Callable[[], None], kind: str = "secondary", width: int | None = None) -> tk.Button:
    palette = {
        "primary": (ACCENT, TEXT, ACCENT_HOVER),
        "success": (GREEN, "#06150e", "#65dfa5"),
        "danger": (RED, "#220509", "#ff8790"),
        "secondary": (PANEL_ALT, TEXT, BORDER),
        "ghost": (PANEL, MUTED, PANEL_ALT),
    }
    bg, fg, active = palette[kind]
    return tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg, activebackground=active,
        activeforeground=fg, relief="flat", bd=0, padx=14, pady=9, cursor="hand2",
        highlightthickness=1, highlightbackground=bg, highlightcolor=ACCENT,
        font=("Segoe UI Semibold", 9), width=width,
    )


class RaidManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1360x820")
        self.minsize(1120, 680)
        self.configure(bg=BG)
        try:
            if ICON_PATH.exists():
                self.iconbitmap(default=str(ICON_PATH))
        except Exception:
            pass

        self.log_lines: list[str] = []
        self.logger = setup_logging(self._append_log_threadsafe)
        self.db = Database(DB_PATH, SEED_PATH)
        try:
            self.db.backup(BACKUP_DIR)
        except Exception as exc:
            self.logger.warning("Не создана резервная копия: %s", exc)
        self.settings = self.db.get_settings()
        self.worker = BrowserWorker()
        self.tray = TrayController(self)
        self.targets: list[Target] = []
        self.target_by_coord: dict[str, Target] = {}
        self.active_flights: list[Flight] = []
        self.notified_returns: set[str] = set()
        self.busy = False
        self.connected = False
        self.current_page = "dashboard"
        self.nav_buttons: dict[str, tk.Button] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.checked_queue_ids: set[int] = set()
        self.asteroid_observations: list[AsteroidObservation] = []
        self.asteroid_plans: list[AsteroidPlan] = []
        self.asteroid_cancel_event = threading.Event()
        self._auto_last = 0.0
        self._health_last = 0.0
        self._asteroid_captcha_last = 0.0
        self._asteroid_captcha_inflight = False
        self._closing = False

        self.status_var = tk.StringVar(value="Браузер не подключён")
        self.page_title_var = tk.StringVar(value="Дашборд")
        self.search_var = tk.StringVar()
        self.min_energy_var = tk.IntVar(value=int(self.settings["min_energy"]))
        self.min_metal_queue_var = tk.IntVar(value=int(self.settings.get("min_metal_for_queue", 480000)))
        self.queue_size_var = tk.IntVar(value=int(self.settings.get("queue_size", 45)))
        self.ship_count_var = tk.IntVar(value=int(self.settings["ship_count"]))
        self.max_slots_var = tk.IntVar(value=int(self.settings["max_slots"]))
        self.repeat_minutes_var = tk.IntVar(value=int(self.settings["repeat_minutes"]))
        self.auto_var = tk.BooleanVar(value=bool(self.settings["auto_enabled"]))
        self.confirm_single_var = tk.BooleanVar(value=bool(self.settings["confirm_single"]))
        self.confirm_wave_var = tk.BooleanVar(value=bool(self.settings["confirm_wave"]))
        self.tray_var = tk.BooleanVar(value=bool(self.settings["minimize_to_tray"]))
        self.notify_var = tk.BooleanVar(value=bool(self.settings["notify_returns"]))
        self.port_var = tk.IntVar(value=int(self.settings["port"]))
        self.home_g_var = tk.IntVar(value=int(self.settings["home_g"]))
        self.home_s_var = tk.IntVar(value=int(self.settings["home_s"]))
        self.home_p_var = tk.IntVar(value=int(self.settings["home_p"]))
        self.auto_interval_var = tk.IntVar(value=int(self.settings["auto_interval_seconds"]))
        self.report_lookback_var = tk.IntVar(value=int(self.settings.get("report_lookback_hours", 24)))
        self.asteroid_home_g_var = tk.IntVar(value=int(self.settings.get("asteroid_home_g", 3)))
        self.asteroid_home_s_var = tk.IntVar(value=int(self.settings.get("asteroid_home_s", 39)))
        self.asteroid_home_p_var = tk.IntVar(value=int(self.settings.get("asteroid_home_p", 8)))
        self.asteroid_galaxy_var = tk.IntVar(value=int(self.settings.get("asteroid_galaxy", 3)))
        self.asteroid_start_system_var = tk.IntVar(value=int(self.settings.get("asteroid_start_system", 39)))
        self.asteroid_end_system_var = tk.IntVar(value=int(self.settings.get("asteroid_end_system", 1)))
        self.asteroid_recyclers_var = tk.IntVar(value=int(self.settings.get("asteroid_recyclers", 5)))
        self.asteroid_max_flights_var = tk.IntVar(value=int(self.settings.get("asteroid_max_flights", 15)))
        self.asteroid_safety_var = tk.IntVar(value=int(self.settings.get("asteroid_safety_seconds", 10)))
        self.asteroid_buffer_var = tk.IntVar(value=int(self.settings.get("asteroid_cycle_buffer_minutes", 5)))
        self.asteroid_auto_var = tk.BooleanVar(value=bool(self.settings.get("asteroid_auto_enabled", False)))
        if self.asteroid_auto_var.get() and self.auto_var.get():
            self.auto_var.set(False)
            self.db.set_setting("auto_enabled", False)
        self.asteroid_next_cycle_at = parse_dt(str(self.settings.get("asteroid_next_cycle_at") or ""))
        self.asteroid_status_var = tk.StringVar(value="Готов к сканированию")
        self.asteroid_candidate_var = tk.StringVar(value="0")
        self.asteroid_ready_var = tk.StringVar(value="0")
        self.asteroid_sent_var = tk.StringVar(value="0")
        self.asteroid_next_var = tk.StringVar(value="—")

        self.card_slots_var = tk.StringVar(value="0 / 15")
        self.card_queue_var = tk.StringVar(value="0")
        self.card_targets_var = tk.StringVar(value="0")
        self.card_return_var = tk.StringVar(value="—")

        self._configure_style()
        self._build_shell()
        self.reload_data()
        self.show_page("dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, self._tick)
        self.logger.info("Запущен %s %s; данные: %s", APP_NAME, APP_VERSION, DATA_DIR)

    # ---------- UI construction ----------
    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=40, borderwidth=0, font=("Segoe UI", 9))
        style.map("Dark.Treeview", background=[("selected", BLUE_DARK), ("!selected", PANEL)],
                  foreground=[("selected", TEXT)])
        style.configure("Dark.Treeview.Heading", background=PANEL_ALT, foreground=MUTED,
                        relief="flat", font=("Segoe UI Semibold", 9), padding=(10, 11))
        style.map("Dark.Treeview.Heading", background=[("active", CARD_GLOW)], foreground=[("active", TEXT)])
        style.configure("Dark.TNotebook", background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 8))
        style.map("Dark.TNotebook.Tab", background=[("selected", PANEL_ALT)], foreground=[("selected", TEXT)])
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT, foreground=TEXT)
        style.configure("TSpinbox", fieldbackground=INPUT, background=INPUT, foreground=TEXT)
        style.configure("Vertical.TScrollbar", background=PANEL_ALT, troughcolor=BG, bordercolor=BG, arrowsize=13)

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = tk.Frame(self, bg=SIDEBAR, width=232, highlightbackground=BORDER, highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        logo = tk.Frame(sidebar, bg=SIDEBAR, padx=22, pady=26)
        logo.pack(fill="x")
        tk.Label(logo, text="NEMEXIA", bg=SIDEBAR, fg=TEXT,
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(logo, text="RAID MANAGER", bg=SIDEBAR, fg=ACCENT,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(3, 0))

        nav = [
            ("dashboard", "⌂  Дашборд"),
            ("queue", "≡  План отправки"),
            ("active", "◷  Активные"),
            ("recon", "◉  Разведка"),
            ("asteroids", "◆  Астероиды"),
            ("targets", "◎  Цели"),
            ("history", "↺  История"),
            ("settings", "⚙  Настройки"),
            ("logs", "≣  Лог"),
        ]
        for key, label in nav:
            button = tk.Button(sidebar, text=label, anchor="w", command=lambda k=key: self.show_page(k),
                               bg=SIDEBAR, fg=MUTED, activebackground=PANEL_ALT, activeforeground=TEXT,
                               relief="flat", bd=0, padx=18, pady=12, cursor="hand2",
                               highlightthickness=0, font=("Segoe UI Semibold", 10))
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = button

        bottom = tk.Frame(sidebar, bg=SIDEBAR, padx=16, pady=18)
        bottom.pack(side="bottom", fill="x")
        make_button(bottom, "Запустить браузер", self.launch_browser, "secondary").pack(fill="x", pady=3)
        make_button(bottom, "Подключиться", self.connect_browser, "primary").pack(fill="x", pady=3)
        tk.Label(bottom, text=f"v{APP_VERSION}", bg=SIDEBAR, fg="#536174",
                 font=("Segoe UI", 8)).pack(anchor="center", pady=(10, 0))

        content = tk.Frame(self, bg=BG)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)

        topbar = tk.Frame(content, bg=BG, padx=28, pady=20)
        topbar.grid(row=0, column=0, sticky="ew")
        tk.Label(topbar, textvariable=self.page_title_var, bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 22)).pack(side="left")
        status = tk.Label(topbar, textvariable=self.status_var, bg=PANEL_ALT, fg=MUTED,
                          padx=14, pady=8, font=("Segoe UI Semibold", 9), highlightbackground=BORDER, highlightthickness=1)
        status.pack(side="right")
        make_button(topbar, "Синхронизировать", self.sync_flights, "secondary").pack(side="right", padx=8)

        self.page_host = tk.Frame(content, bg=BG)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)

        self._build_dashboard()
        self._build_queue_page()
        self._build_active_page()
        self._build_recon_page()
        self._build_asteroids_page()
        self._build_targets_page()
        self._build_history_page()
        self._build_settings_page()
        self._build_logs_page()

    def _new_page(self, key: str) -> tk.Frame:
        frame = tk.Frame(self.page_host, bg=BG)
        frame.grid(row=0, column=0, sticky="nsew")
        self.pages[key] = frame
        return frame

    def _card(self, parent: tk.Misc, title: str, variable: tk.StringVar, subtitle: str) -> tk.Frame:
        card = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, padx=18, pady=16)
        tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(card, textvariable=variable, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 24)).pack(anchor="w", pady=(6, 2))
        tk.Label(card, text=subtitle, bg=PANEL, fg="#6f829a", font=("Segoe UI", 8)).pack(anchor="w")
        return card

    def _tree(self, parent: tk.Misc, columns: tuple[str, ...], headings: dict[str, str], widths: dict[str, int],
              selectmode: str = "browse") -> tuple[ttk.Treeview, ttk.Scrollbar]:
        tree = ttk.Treeview(parent, columns=columns, show="headings", style="Dark.Treeview", selectmode=selectmode)
        for column in columns:
            tree.heading(column, text=headings.get(column, column),
                         command=lambda col=column, view=tree: self._sort_tree(view, col))
            tree.column(column, width=widths.get(column, 100), minwidth=45, anchor="center")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        return tree, scroll

    def _sort_tree(self, tree: ttk.Treeview, column: str) -> None:
        """Sort the visible table by a clicked header without changing queue priority."""
        state = getattr(self, "_tree_sort_state", {})
        reverse = not state.get((str(tree), column), False)
        state[(str(tree), column)] = reverse
        self._tree_sort_state = state

        def value(item: str) -> tuple[int, Any]:
            raw = tree.set(item, column).strip()
            try:
                return (0, float(raw.replace(" ", "").replace(",", ".")))
            except ValueError:
                pass
            try:
                return (0, datetime.strptime(raw, "%d.%m.%Y %H:%M:%S"))
            except ValueError:
                return (1, raw.casefold())

        for index, item in enumerate(sorted(tree.get_children(""), key=value, reverse=reverse)):
            tree.move(item, "", index)

    def _section(self, parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        panel = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        header = tk.Frame(panel, bg=PANEL, padx=18, pady=14)
        header.pack(fill="x")
        tk.Label(header, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 12)).pack(side="left")
        if subtitle:
            tk.Label(header, text=subtitle, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=10)
        return panel

    def _build_dashboard(self) -> None:
        page = self._new_page("dashboard")
        cards = tk.Frame(page, bg=BG)
        cards.pack(fill="x")
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1)
        self._card(cards, "ЗАНЯТО СЛОТОВ", self.card_slots_var, "атаки / лимит").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._card(cards, "В ОЧЕРЕДИ", self.card_queue_var, "готовы к отправке").grid(row=0, column=1, sticky="ew", padx=8)
        self._card(cards, "ЦЕЛЕЙ ПО МЕТАЛЛУ", self.card_targets_var, "есть актуальная разведка").grid(row=0, column=2, sticky="ew", padx=8)
        self._card(cards, "БЛИЖАЙШИЙ ВОЗВРАТ", self.card_return_var, "реальный таймер игры").grid(row=0, column=3, sticky="ew", padx=(8, 0))

        actions = tk.Frame(page, bg=BG, pady=14)
        actions.pack(fill="x")
        make_button(actions, "Импортировать отчёты", self.import_from_browser, "secondary").pack(side="left", padx=(0, 7))
        make_button(actions, "Рассчитать времена", self.calculate_times, "secondary").pack(side="left", padx=7)
        make_button(actions, "Сформировать план", self.generate_queue, "primary").pack(side="left", padx=7)
        make_button(actions, "Отправить следующий", self.send_next, "success").pack(side="left", padx=7)
        self.auto_badge = tk.Label(actions, text="АВТО ВЫКЛ", bg=PANEL, fg=MUTED, padx=10, pady=7,
                                   font=("Segoe UI Semibold", 8))
        self.auto_badge.pack(side="right")

        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        recommended = self._section(body, "Рекомендованные цели", "больше металла — выше; только с данными разведки")
        recommended.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tree_frame = tk.Frame(recommended, bg=PANEL, padx=8, pady=8)
        tree_frame.pack(fill="both", expand=True)
        cols = ("rank", "player", "coord", "metal", "trip", "last")
        self.dashboard_tree, scroll = self._tree(
            tree_frame, cols,
            {"rank": "#", "player": "Игрок", "coord": "Координаты", "metal": "Металл",
             "trip": "Цикл", "last": "Последняя отправка"},
            {"rank": 45, "player": 120, "coord": 90, "metal": 100, "trip": 75, "last": 140},
        )
        self.dashboard_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.dashboard_tree.bind("<Double-1>", lambda _: self.send_selected_dashboard())

        active = self._section(body, "Активные атаки", "до прибытия и возврата")
        active.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        active_frame = tk.Frame(active, bg=PANEL, padx=8, pady=8)
        active_frame.pack(fill="both", expand=True)
        cols2 = ("target", "arrival", "return")
        self.dashboard_active_tree, scroll2 = self._tree(
            active_frame, cols2,
            {"target": "Цель", "arrival": "До удара", "return": "До возврата"},
            {"target": 95, "arrival": 100, "return": 100},
        )
        self.dashboard_active_tree.pack(side="left", fill="both", expand=True)
        scroll2.pack(side="right", fill="y")

    def _build_queue_page(self) -> None:
        page = self._new_page("queue")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        tk.Label(toolbar, text="Размер плана", bg=BG, fg=MUTED).pack(side="left")
        tk.Spinbox(toolbar, from_=1, to=200, textvariable=self.queue_size_var, width=5,
                   bg=PANEL_ALT, fg=TEXT, buttonbackground=PANEL_ALT, insertbackground=TEXT,
                   relief="flat").pack(side="left", padx=(8, 14), ipady=5)
        make_button(toolbar, "Сформировать по металлу", self.generate_queue, "primary").pack(side="left", padx=4)
        make_button(toolbar, "Отправить следующий", self.send_next, "success").pack(side="left", padx=4)
        make_button(toolbar, "Отправить отмеченную волну", self.send_wave, "success").pack(side="left", padx=4)
        make_button(toolbar, "Подготовить", self.prepare_selected_queue, "secondary").pack(side="left", padx=4)
        make_button(toolbar, "Снять зависшие статусы", self.reset_stuck_sending, "secondary").pack(side="left", padx=4)
        make_button(toolbar, "↑", lambda: self.move_queue(-1), "ghost").pack(side="right", padx=3)
        make_button(toolbar, "↓", lambda: self.move_queue(1), "ghost").pack(side="right", padx=3)
        make_button(toolbar, "Удалить", self.remove_queue_selected, "danger").pack(side="right", padx=3)
        make_button(toolbar, "Очистить", self.clear_queue, "secondary").pack(side="right", padx=3)

        panel = self._section(page, "План отправки", "поставьте галочки для волны; без галочек «следующий» идёт по металлу")
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("picked", "position", "coord", "player", "energy", "metal", "minerals", "resource_gas", "total", "spy_at", "trip", "score", "last", "state")
        self.queue_tree, scroll = self._tree(
            frame, cols,
            {"picked": "✓", "position": "#", "coord": "Координаты", "player": "Игрок", "energy": "Энергия",
             "metal": "Металл", "minerals": "Минералы", "resource_gas": "Газ", "total": "Всего", "spy_at": "Разведка",
             "trip": "Полный цикл", "score": "Приоритет", "last": "Последняя отправка", "state": "Статус"},
            {"picked": 38, "position": 45, "coord": 95, "player": 140, "energy": 90, "trip": 100,
             "metal": 85, "minerals": 85, "resource_gas": 85, "total": 95, "spy_at": 145,
             "score": 95, "last": 150, "state": 90},
            selectmode="extended",
        )
        self.queue_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.queue_tree.bind("<Button-1>", self._toggle_queue_checkbox)
        self.queue_tree.tag_configure("active", background="#15312a")
        self.queue_tree.tag_configure("sending", background="#1b315d")
        self.queue_tree.tag_configure("failed", background="#44212a")
        self.queue_tree.tag_configure("sent", foreground="#77869a")

    def _build_active_page(self) -> None:
        page = self._new_page("active")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        make_button(toolbar, "Синхронизировать с игрой", self.sync_flights, "primary").pack(side="left")
        panel = self._section(page, "Активные атаки", "таймеры считываются из Nemexia")
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("target", "player", "fleet", "arrival_at", "arrival_left", "return_at", "return_left")
        self.active_tree, scroll = self._tree(
            frame, cols,
            {"target": "Цель", "player": "Игрок", "fleet": "Fleet ID", "arrival_at": "Прибытие",
             "arrival_left": "До удара", "return_at": "Возврат", "return_left": "До возврата"},
            {"target": 95, "player": 150, "fleet": 90, "arrival_at": 100,
             "arrival_left": 105, "return_at": 100, "return_left": 105},
        )
        self.active_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_recon_page(self) -> None:
        page = self._new_page("recon")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        make_button(toolbar, "Собрать историю докладов", self.collect_combat_history, "primary").pack(side="left", padx=4)
        make_button(toolbar, "Обновить разведку", self.refresh_spy_reports, "secondary").pack(side="left", padx=4)
        make_button(toolbar, "Полное обновление данных", self.full_refresh, "success").pack(side="left", padx=4)
        tk.Label(toolbar, text="Ресурсы — снимок на время последней разведки", bg=BG, fg=MUTED).pack(side="right")
        panel = self._section(page, "Разведка", "история снимков сохраняется; сообщения не удаляются")
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("date", "coord", "energy", "metal", "minerals", "gas", "population", "ships", "defense", "status")
        self.recon_tree, scroll = self._tree(
            frame, cols,
            {"date": "Разведка", "coord": "Координаты", "energy": "Энергия", "metal": "Металл",
             "minerals": "Минералы", "gas": "Газ", "population": "Население", "ships": "Корабли",
             "defense": "Оборона", "status": "Полнота"},
            {"date": 145, "coord": 95, "energy": 85, "metal": 85, "minerals": 85, "gas": 85,
             "population": 95, "ships": 85, "defense": 85, "status": 90},
        )
        self.recon_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_asteroids_page(self) -> None:
        page = self._new_page("asteroids")

        controls = self._section(
            page,
            "Добыча с астероидов",
            "Питер → системы 39…1 → 5 переработчиков → миссия «Добыча газа»",
        )
        controls.pack(fill="x", pady=(0, 12))
        row1 = tk.Frame(controls, bg=PANEL, padx=14, pady=8)
        row1.pack(fill="x")

        def label_spin(parent: tk.Misc, label: str, var: tk.Variable, start: int, end: int, width: int = 5) -> None:
            block = tk.Frame(parent, bg=PANEL)
            block.pack(side="left", padx=(0, 16))
            tk.Label(block, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
            tk.Spinbox(
                block, from_=start, to=end, textvariable=var, width=width,
                bg=PANEL_ALT, fg=TEXT, buttonbackground=PANEL_ALT,
                insertbackground=TEXT, relief="flat",
            ).pack(anchor="w", pady=(4, 0), ipady=4)

        label_spin(row1, "Рейсов", self.asteroid_max_flights_var, 1, 100)
        label_spin(row1, "Переработчиков / рейс", self.asteroid_recyclers_var, 1, 1000, 7)
        label_spin(row1, "Стартовая система", self.asteroid_start_system_var, 1, 40)
        label_spin(row1, "До системы", self.asteroid_end_system_var, 1, 40)
        label_spin(row1, "Запас до движения, сек", self.asteroid_safety_var, 0, 300, 7)
        label_spin(row1, "Пауза после возврата, мин", self.asteroid_buffer_var, 0, 120, 7)

        home = tk.Frame(row1, bg=PANEL)
        home.pack(side="left", padx=(0, 16))
        tk.Label(home, text="Исходная планета", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        home_inputs = tk.Frame(home, bg=PANEL)
        home_inputs.pack(anchor="w", pady=(4, 0))
        for var in (self.asteroid_home_g_var, self.asteroid_home_s_var, self.asteroid_home_p_var):
            tk.Spinbox(
                home_inputs, from_=1, to=999, textvariable=var, width=3,
                bg=PANEL_ALT, fg=TEXT, buttonbackground=PANEL_ALT,
                insertbackground=TEXT, relief="flat",
            ).pack(side="left", padx=(0, 3), ipady=4)

        actions = tk.Frame(controls, bg=PANEL, padx=14, pady=10)
        actions.pack(fill="x")
        make_button(actions, "Сканировать", self.scan_asteroids_manual, "primary").pack(side="left", padx=(0, 6))
        make_button(actions, "Рассчитать волну", self.calculate_asteroid_wave, "secondary").pack(side="left", padx=6)
        make_button(actions, "Отправить волну", self.send_asteroid_wave, "success").pack(side="left", padx=6)
        self.asteroid_auto_button = make_button(
            actions, "Запустить автопродление", self.toggle_asteroid_auto, "secondary"
        )
        self.asteroid_auto_button.pack(side="left", padx=6)
        make_button(actions, "Остановить операцию", self.cancel_asteroid_operation, "danger").pack(side="left", padx=6)
        self.asteroid_auto_badge = tk.Label(
            actions, text="АВТО ВЫКЛ", bg=PANEL_ALT, fg=MUTED, padx=12, pady=8,
            font=("Segoe UI Semibold", 8),
        )
        self.asteroid_auto_badge.pack(side="right")

        cards = tk.Frame(page, bg=BG)
        cards.pack(fill="x", pady=(0, 12))
        for column in range(5):
            cards.grid_columnconfigure(column, weight=1)
        self._card(cards, "СТАТУС", self.asteroid_status_var, "текущий этап").grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        self._card(cards, "КАНДИДАТОВ", self.asteroid_candidate_var, "обнаружено сканированием").grid(
            row=0, column=1, sticky="ew", padx=8
        )
        self._card(cards, "ГОТОВО", self.asteroid_ready_var, "рассчитано для отправки").grid(
            row=0, column=2, sticky="ew", padx=8
        )
        self._card(cards, "ОТПРАВЛЕНО", self.asteroid_sent_var, "в последнем цикле").grid(
            row=0, column=3, sticky="ew", padx=8
        )
        self._card(cards, "СЛЕДУЮЩИЙ ЦИКЛ", self.asteroid_next_var, "возврат последнего + запас").grid(
            row=0, column=4, sticky="ew", padx=(8, 0)
        )

        panel = self._section(
            page,
            "Астероиды и рассчитанные рейсы",
            "позиция автоматически переносится через 24: 3:38:24 → 3:39:1",
        )
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("origin", "scanned", "next", "period", "one", "target", "shifts", "return", "status")
        self.asteroid_tree, scroll = self._tree(
            frame, cols,
            {
                "origin": "Найден", "scanned": "Время скана", "next": "След. движение",
                "period": "Период", "one": "Полёт туда", "target": "Цель при прилёте",
                "shifts": "Сдвигов", "return": "Полный цикл", "status": "Статус",
            },
            {
                "origin": 95, "scanned": 145, "next": 145, "period": 80, "one": 90,
                "target": 110, "shifts": 70, "return": 100, "status": 220,
            },
            selectmode="extended",
        )
        self.asteroid_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.asteroid_tree.tag_configure("ready", background="#15312a")
        self.asteroid_tree.tag_configure("sent", foreground="#6fbf9c")
        self.asteroid_tree.tag_configure("error", background="#44212a")

    def _build_targets_page(self) -> None:
        page = self._new_page("targets")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        tk.Label(toolbar, text="Поиск", bg=BG, fg=MUTED).pack(side="left")
        search = tk.Entry(toolbar, textvariable=self.search_var, bg=PANEL_ALT, fg=TEXT,
                          insertbackground=TEXT, relief="flat", width=22)
        search.pack(side="left", padx=(7, 14), ipady=6)
        search.bind("<KeyRelease>", lambda _: self.render_targets())
        tk.Label(toolbar, text="Мин. энергия", bg=BG, fg=MUTED).pack(side="left")
        spin = tk.Spinbox(toolbar, from_=0, to=100000, increment=500, textvariable=self.min_energy_var,
                          width=8, bg=PANEL_ALT, fg=TEXT, buttonbackground=PANEL_ALT,
                          insertbackground=TEXT, relief="flat", command=self.render_all)
        spin.pack(side="left", padx=(7, 14), ipady=5)
        spin.bind("<KeyRelease>", lambda _: self.render_all())
        make_button(toolbar, "Из браузера", self.import_from_browser, "primary").pack(side="left", padx=4)
        make_button(toolbar, "Из ZIP / HTML", self.import_from_files, "secondary").pack(side="left", padx=4)
        make_button(toolbar, "Добавить", self.add_target, "secondary").pack(side="right", padx=4)
        make_button(toolbar, "Изменить", self.edit_target, "secondary").pack(side="right", padx=4)
        make_button(toolbar, "Удалить", self.delete_target, "danger").pack(side="right", padx=4)

        panel = self._section(page, "База целей", "сверху больше металла; ресурсы берутся из последней разведки")
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("flag", "coord", "player", "energy", "metal", "minerals", "resource_gas", "snapshot", "age", "loot", "one", "round", "score", "last", "returned", "count", "notes")
        self.targets_tree, scroll = self._tree(
            frame, cols,
            {"flag": "", "coord": "Координаты", "player": "Игрок", "energy": "Энергия",
             "metal": "Металл", "minerals": "Минералы", "resource_gas": "Газ", "snapshot": "Разведка", "age": "Возраст",
             "loot": "Посл. добыча", "one": "Туда", "round": "Цикл", "score": "Металл / приоритет", "last": "Последняя отправка",
             "returned": "Последний возврат", "count": "Рейдов", "notes": "Заметка"},
            {"flag": 40, "coord": 95, "player": 140, "energy": 90, "one": 80, "round": 80,
             "metal": 85, "minerals": 85, "resource_gas": 85, "snapshot": 145, "age": 80, "loot": 95,
             "score": 90, "last": 150, "returned": 150, "count": 65, "notes": 170},
            selectmode="extended",
        )
        self.targets_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.targets_tree.bind("<Double-1>", lambda _: self.edit_target())
        self.targets_tree.tag_configure("black", foreground="#6a7686")
        self.targets_tree.tag_configure("disabled", foreground="#56606e")
        self.targets_tree.tag_configure("active", background="#15312a")

    def _build_history_page(self) -> None:
        page = self._new_page("history")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        make_button(toolbar, "Экспорт CSV", self.export_history, "secondary").pack(side="left")
        panel = self._section(page, "История рейсов", "успешные отправки и ошибки")
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
        frame.pack(fill="both", expand=True)
        cols = ("sent", "target", "player", "ships", "arrival", "return", "fleet", "status", "error")
        self.history_tree, scroll = self._tree(
            frame, cols,
            {"sent": "Отправлен", "target": "Цель", "player": "Игрок", "ships": "МТ",
             "arrival": "Прибытие", "return": "Возврат", "fleet": "Fleet ID",
             "status": "Статус", "error": "Ошибка"},
            {"sent": 145, "target": 90, "player": 125, "ships": 55, "arrival": 145,
             "return": 145, "fleet": 80, "status": 75, "error": 250},
        )
        self.history_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _setting_row(self, parent: tk.Misc, row: int, label: str, widget: tk.Widget, note: str = "") -> None:
        tk.Label(parent, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 9)).grid(
            row=row, column=0, sticky="w", padx=16, pady=10
        )
        widget.grid(row=row, column=1, sticky="w", padx=10, pady=10)
        if note:
            tk.Label(parent, text=note, bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).grid(
                row=row, column=2, sticky="w", padx=10, pady=10
            )

    def _build_settings_page(self) -> None:
        page = self._new_page("settings")
        panel = self._section(page, "Настройки", "автоотправка выключена по умолчанию")
        panel.pack(fill="both", expand=True)
        form = tk.Frame(panel, bg=PANEL)
        form.pack(fill="x", pady=(0, 10))
        form.grid_columnconfigure(2, weight=1)

        def spin(var: tk.Variable, start: int, end: int, width: int = 8) -> tk.Spinbox:
            return tk.Spinbox(form, from_=start, to=end, textvariable=var, width=width,
                              bg=PANEL_ALT, fg=TEXT, buttonbackground=PANEL_ALT,
                              insertbackground=TEXT, relief="flat")

        self._setting_row(form, 0, "CDP-порт", spin(self.port_var, 1024, 65535), "обычно 9222")
        home = tk.Frame(form, bg=PANEL)
        for var in (self.home_g_var, self.home_s_var, self.home_p_var):
            tk.Spinbox(home, from_=1, to=999, textvariable=var, width=4, bg=PANEL_ALT, fg=TEXT,
                       buttonbackground=PANEL_ALT, insertbackground=TEXT, relief="flat").pack(side="left", padx=2)
        self._setting_row(form, 1, "Исходная планета", home, "Москва: 3 : 39 : 11")
        self._setting_row(form, 2, "Мегатранспортировщиков", spin(self.ship_count_var, 1, 100000), "на один рейс")
        self._setting_row(form, 3, "Максимум слотов", spin(self.max_slots_var, 1, 100), "сейчас 15")
        self._setting_row(form, 4, "Мин. энергия", spin(self.min_energy_var, 0, 100000), "старый параметр; на план отправки не влияет")
        self._setting_row(form, 5, "Мин. металл для плана", spin(self.min_metal_queue_var, 0, 100000000, 10), "по умолчанию 480 000; ниже цели не попадают в план")
        self._setting_row(form, 6, "Интервал повторного рейса", spin(self.repeat_minutes_var, 1, 1440), "сохраняется для истории; на порядок по металлу не влияет")
        self._setting_row(form, 7, "Автоинтервал", spin(self.auto_interval_var, 10, 3600), "секунд между попытками")
        self._setting_row(form, 8, "Глубина докладов", spin(self.report_lookback_var, 1, 720), "часов: старые страницы не импортируются")

        def check(var: tk.BooleanVar, text: str, command: Callable[[], None] | None = None) -> tk.Checkbutton:
            return tk.Checkbutton(form, text=text, variable=var, command=command, bg=PANEL, fg=TEXT,
                                  activebackground=PANEL, activeforeground=TEXT, selectcolor=PANEL_ALT)

        self._setting_row(form, 9, "Автоматический режим", check(self.auto_var, "Автоматически отправлять план", self.toggle_auto),
                          "волна из свободных слотов; остановка при ошибке")
        self._setting_row(form, 10, "Подтверждения", check(self.confirm_single_var, "Одиночный рейс"), "")
        self._setting_row(form, 11, "", check(self.confirm_wave_var, "Волна рейсов"), "")
        self._setting_row(form, 12, "Уведомления", check(self.notify_var, "Сообщать о возврате"), "через трей / системный звук")
        self._setting_row(form, 13, "Закрытие окна", check(self.tray_var, "Сворачивать в трей"), "")

        actions = tk.Frame(panel, bg=PANEL, padx=16, pady=14)
        actions.pack(fill="x")
        make_button(actions, "Сохранить настройки", self.save_settings, "primary").pack(side="left")
        make_button(actions, "Создать резервную копию", self.manual_backup, "secondary").pack(side="left", padx=8)
        make_button(actions, "Открыть папку данных", self.open_data_dir, "secondary").pack(side="left", padx=8)
        make_button(actions, "Собрать EXE", self.show_build_info, "ghost").pack(side="right")

    def _build_logs_page(self) -> None:
        page = self._new_page("logs")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        make_button(toolbar, "Очистить экран", self.clear_log_view, "secondary").pack(side="left")
        make_button(toolbar, "Открыть папку логов", lambda: self._open_folder(LOG_DIR), "secondary").pack(side="left", padx=8)
        panel = self._section(page, "Технический лог", "при ошибке автоматически сохраняется скриншот страницы")
        panel.pack(fill="both", expand=True)
        self.log_text = tk.Text(panel, bg="#0a0f15", fg="#b8c5d5", insertbackground=TEXT,
                                relief="flat", font=("Consolas", 9), padx=12, pady=12, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        for line in self.log_lines:
            self.log_text.insert("end", line + "\n")
        self.log_text.configure(state="disabled")

    # ---------- Navigation and rendering ----------
    def show_page(self, key: str) -> None:
        titles = {
            "dashboard": "Дашборд", "queue": "План отправки", "active": "Активные рейсы",
            "recon": "Разведка", "asteroids": "Астероиды", "targets": "Цели", "history": "История",
            "settings": "Настройки", "logs": "Лог",
        }
        self.current_page = key
        self.page_title_var.set(titles[key])
        self.pages[key].tkraise()
        for nav_key, button in self.nav_buttons.items():
            button.configure(bg=PANEL_ALT if nav_key == key else SIDEBAR,
                             fg=TEXT if nav_key == key else MUTED)
        self.render_all()

    def reload_data(self) -> None:
        self.targets = self.db.list_targets()
        self.target_by_coord = {target.coord: target for target in self.targets}
        self.render_all()

    def render_all(self) -> None:
        if not self.pages:
            return
        self.render_dashboard()
        self.render_queue()
        self.render_active()
        self.render_recon()
        self.render_asteroids()
        self.render_targets()
        self.render_history()
        self.auto_badge.configure(text="АВТО ВКЛ" if self.auto_var.get() else "АВТО ВЫКЛ",
                                  fg=GREEN if self.auto_var.get() else MUTED)
        if hasattr(self, "asteroid_auto_badge"):
            enabled = bool(self.asteroid_auto_var.get())
            self.asteroid_auto_badge.configure(
                text="АВТО ВКЛ" if enabled else "АВТО ВЫКЛ",
                fg=GREEN if enabled else MUTED,
            )
            self.asteroid_auto_button.configure(
                text="Остановить автопродление" if enabled else "Запустить автопродление"
            )

    def _active_coords(self) -> set[str]:
        return {flight.target.replace(" ", "") for flight in self.active_flights}

    def ranked_targets(self, exclude_active: bool = True) -> list[tuple[Target, float]]:
        active = self._active_coords() if exclude_active else set()
        minimum_metal = max(0, self._safe_int(self.min_metal_queue_var, 480000))
        ranked = []
        for target in self.targets:
            if (
                not target.enabled
                or target.blacklisted
                or target.coord in active
                or target.last_spy_at is None
                or target.metal is None
                or target.metal < minimum_metal
            ):
                continue
            ranked.append((target, float(target.metal)))
        ranked.sort(key=lambda item: (-item[1], item[0].coord))
        return ranked

    def render_dashboard(self) -> None:
        now = utc_now()
        ranked = self.ranked_targets()
        queue = self.db.list_queue()
        max_slots = self._safe_int(self.max_slots_var, 15)
        self.card_slots_var.set(f"{len(self.active_flights)} / {max_slots}")
        self.card_queue_var.set(str(sum(1 for item in queue if item.state == "queued")))
        self.card_targets_var.set(str(len(ranked)))
        next_return = min((f.return_at for f in self.active_flights if f.return_at), default=None)
        self.card_return_var.set(remaining(next_return, now))

        self._clear_tree(self.dashboard_tree)
        for rank, (target, score) in enumerate(ranked[:15], start=1):
            self.dashboard_tree.insert("", "end", iid=f"dash:{target.coord}", values=(
                rank, target.player, target.coord, format_number(target.metal),
                format_duration(target.round_trip_seconds),
                format_datetime(target.last_raid_at) if target.last_raid_at else "нет данных",
            ))
        self._clear_tree(self.dashboard_active_tree)
        for flight in sorted(self.active_flights, key=lambda x: x.return_at or datetime.max.replace(tzinfo=timezone.utc))[:20]:
            self.dashboard_active_tree.insert("", "end", values=(
                flight.target, remaining(flight.arrival_at, now), remaining(flight.return_at, now)
            ))

    def render_queue(self) -> None:
        self._clear_tree(self.queue_tree)
        active = self._active_coords()
        queue_items = self.db.list_queue()
        self.checked_queue_ids.intersection_update(item.id for item in queue_items if item.state == "queued")
        for item in queue_items:
            target = self.target_by_coord.get(item.coord)
            if not target:
                continue
            resources = (target.metal, target.minerals, target.resource_gas)
            resource_total = sum(value or 0 for value in resources) if any(value is not None for value in resources) else None
            state_map = {"queued": "Готов", "sending": "Отправка", "failed": "Ошибка", "done": "Отправлено"}
            is_active = item.coord in active
            status = "В полёте" if is_active else state_map.get(item.state, item.state)
            tag = "active" if is_active else item.state if item.state in {"sending", "failed", "done"} else ""
            self.queue_tree.insert("", "end", iid=f"q:{item.id}", tags=(tag,) if tag else (), values=(
                "☑" if item.id in self.checked_queue_ids else "☐", item.position, target.coord, target.player, format_number(target.energy),
                format_number(target.metal), format_number(target.minerals), format_number(target.resource_gas),
                format_number(resource_total),
                format_datetime(target.last_spy_at) if target.last_spy_at else "нет разведки",
                format_duration(target.round_trip_seconds), format_number(target.metal),
                format_datetime(target.last_raid_at) if target.last_raid_at else "нет данных",
                status,
            ))

    def render_active(self) -> None:
        self._clear_tree(self.active_tree)
        now = utc_now()
        for flight in sorted(self.active_flights, key=lambda x: x.return_at or datetime.max.replace(tzinfo=timezone.utc)):
            target = self.target_by_coord.get(flight.target.replace(" ", ""))
            self.active_tree.insert("", "end", values=(
                flight.target, target.player if target else flight.player, flight.fleet_id or "—",
                format_clock(flight.arrival_at), remaining(flight.arrival_at, now),
                format_clock(flight.return_at), remaining(flight.return_at, now),
            ))

    def render_targets(self) -> None:
        self._clear_tree(self.targets_tree)
        query = self.search_var.get().strip().lower()
        active = self._active_coords()
        now = utc_now()
        targets = [t for t in self.targets if not query or query in t.coord or query in t.player.lower() or query in t.notes.lower()]
        targets.sort(key=lambda t: (t.blacklisted, not t.enabled, -(t.metal or 0), t.coord))
        for target in targets:
            flag = "⛔" if target.blacklisted else ("●" if target.enabled else "○")
            tags = ("black",) if target.blacklisted else (("disabled",) if not target.enabled else (("active",) if target.coord in active else ()))
            self.targets_tree.insert("", "end", iid=f"t:{target.coord}", values=(
                flag, target.coord, target.player, format_number(target.energy),
                format_number(target.metal), format_number(target.minerals), format_number(target.resource_gas),
                format_datetime(target.last_spy_at) if target.last_spy_at else "нет данных",
                f"{format_duration((now - target.last_spy_at).total_seconds())} назад" if target.last_spy_at else "нет разведки",
                format_number(target.last_loot_total),
                format_duration(target.one_way_seconds), format_duration(target.round_trip_seconds),
                format_number(target.metal),
                format_datetime(target.last_raid_at) if target.last_raid_at else "нет данных",
                format_datetime(target.last_return_at) if target.last_return_at else "нет данных",
                target.raid_count, target.notes,
            ), tags=tags)

    def render_history(self) -> None:
        self._clear_tree(self.history_tree)
        for row in self.db.list_history(1000):
            self.history_tree.insert("", "end", values=(
                (format_datetime(parse_dt(row["sent_at"])) if row["sent_at"] else "время отправки неизвестно"), row["target"], row["player"] or "—",
                row["ship_count"] or "—", format_datetime(parse_dt(row["arrival_at"])),
                format_datetime(parse_dt(row["return_at"])), row["fleet_id"] or "—",
                "ОК" if row["status"] == "sent" else row["status"], row["error"] or "",
            ))

    def render_recon(self) -> None:
        if not hasattr(self, "recon_tree"):
            return
        self._clear_tree(self.recon_tree)
        for row in self.db.list_latest_spy_reports(1000):
            self.recon_tree.insert("", "end", values=(
                format_datetime(parse_dt(row["report_at"])), row["target_coord"], format_number(row["energy"]),
                format_number(row["metal"]), format_number(row["minerals"]), format_number(row["gas"]),
                format_number(row["population"]), format_number(row["ships"]), format_number(row["defense"]),
                row["completeness"] or "—",
            ))

    @staticmethod
    def _format_server_datetime(value: datetime | None) -> str:
        return value.strftime("%d.%m.%Y %H:%M:%S") if value else "—"

    def render_asteroids(self) -> None:
        if not hasattr(self, "asteroid_tree"):
            return
        self._clear_tree(self.asteroid_tree)
        observations = list(self.asteroid_observations)
        if not observations:
            for row in self.db.list_latest_asteroid_scans(200):
                last_move = parse_dt(row["last_move_server"])
                next_move = parse_dt(row["next_move_server"])
                scanned = parse_dt(row["scanned_server_at"])
                if not last_move or not next_move or not scanned:
                    continue
                observations.append(AsteroidObservation(
                    g=int(row["g"]), s=int(row["s"]), p=int(row["p"]),
                    last_move_server=last_move.replace(tzinfo=None),
                    next_move_server=next_move.replace(tzinfo=None),
                    period_seconds=int(row["period_seconds"]),
                    scanned_server_at=scanned.replace(tzinfo=None),
                    tooltip_html=row["tooltip_html"] or "",
                    status=row["status"] or "found",
                    error=row["error"],
                ))
        plan_map = {plan.observation.coord: plan for plan in self.asteroid_plans}
        flight_map: dict[str, Any] = {}
        for row in self.db.list_asteroid_flights(500):
            flight_map.setdefault(row["origin_coord"], row)
        for index, observation in enumerate(observations, start=1):
            plan = plan_map.get(observation.coord)
            flight = flight_map.get(observation.coord)
            if flight:
                status = "Отправлен"
                target = flight["target_coord"]
                shifts = flight["shifts"]
                one = format_duration(flight["one_way_seconds"])
                round_trip = format_duration(flight["round_trip_seconds"])
                tag = "sent"
            elif plan:
                status = "Готов"
                target = plan.target_coord
                shifts = plan.shifts
                one = format_duration(plan.one_way_seconds)
                round_trip = format_duration(plan.round_trip_seconds)
                tag = "ready"
            else:
                status = observation.error or "Найден"
                target = "—"
                shifts = "—"
                one = "—"
                round_trip = "—"
                tag = "error" if observation.error else ""
            self.asteroid_tree.insert("", "end", iid=f"a:{index}:{observation.coord}", values=(
                observation.coord,
                self._format_server_datetime(observation.scanned_server_at),
                self._format_server_datetime(observation.next_move_server),
                format_duration(observation.period_seconds),
                one,
                target,
                shifts,
                round_trip,
                status,
            ), tags=(tag,) if tag else ())
        self.asteroid_candidate_var.set(str(len(observations)))
        self.asteroid_ready_var.set(str(len(self.asteroid_plans)))
        last_cycle = self.db.list_asteroid_cycles(1)
        if last_cycle:
            self.asteroid_sent_var.set(str(last_cycle[0]["sent"] or 0))
        if self.asteroid_next_cycle_at:
            self.asteroid_next_var.set(remaining(self.asteroid_next_cycle_at, utc_now()))
        else:
            self.asteroid_next_var.set("—")

    @staticmethod
    def _clear_tree(tree: ttk.Treeview) -> None:
        children = tree.get_children()
        if children:
            tree.delete(*children)

    @staticmethod
    def _safe_int(var: tk.Variable, fallback: int) -> int:
        try:
            return int(var.get())
        except Exception:
            return fallback

    # ---------- Browser tasks ----------
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._safe_int(self.port_var, 9222)}"

    def home(self) -> tuple[int, int, int]:
        return (self._safe_int(self.home_g_var, 3), self._safe_int(self.home_s_var, 39), self._safe_int(self.home_p_var, 11))

    def run_task(self, coroutine: Coroutine[Any, Any, Any], busy_text: str,
                 on_success: Callable[[Any], None] | None = None,
                 on_error: Callable[[Exception], None] | None = None,
                 silent: bool = False) -> None:
        if self.busy:
            if not silent:
                messagebox.showinfo(APP_NAME, "Дождись завершения текущей операции")
            return
        self.busy = True
        self.status_var.set(busy_text)
        future = self.worker.submit(coroutine)

        def poll() -> None:
            if not future.done():
                self.after(100, poll)
                return
            self.busy = False
            try:
                result = future.result()
            except Exception as exc:
                self.status_var.set("Ошибка")
                self.logger.error("%s", exc)
                if on_error:
                    on_error(exc)
                elif not silent:
                    messagebox.showerror(APP_NAME, str(exc))
                return
            if on_success:
                on_success(result)
            elif self.connected:
                self.status_var.set("Подключено")

        self.after(100, poll)

    def launch_browser(self) -> None:
        port = self._safe_int(self.port_var, 9222)
        if cdp_is_available(port):
            self.status_var.set(f"Браузер уже запущен · порт {port}")
            return
        try:
            launch_yandex(port)
            self.status_var.set("Яндекс Браузер запускается…")
            self.logger.info("Запущен отдельный профиль Яндекс Браузера на порту %s", port)
            self.after(1800, self.connect_browser)
        except Exception as exc:
            self.logger.error("Ошибка запуска браузера: %s", exc)
            messagebox.showerror(APP_NAME, str(exc))

    def connect_browser(self, silent: bool = False) -> None:
        endpoint = self.endpoint()
        async def operation():
            return await self.worker.connect(endpoint)

        def success(result: dict[str, Any]) -> None:
            self.connected = True
            self.status_var.set("Подключено")
            self.logger.info("Подключено к вкладке: %s", result["url"])
            self.sync_flights(silent=True)

        def error(_: Exception) -> None:
            self.connected = False

        self.run_task(operation(), "Подключение…", success, error, silent=silent)

    def sync_flights(self, silent: bool = False) -> None:
        endpoint = self.endpoint()
        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.sync_flights()

        def success(flights: list[Flight]) -> None:
            self.connected = True
            self.active_flights = flights
            imported = self.db.sync_history_from_flights(flights)
            self.status_var.set(f"Подключено · атак: {len(flights)}")
            self.logger.info("Синхронизировано активных атак: %s", len(flights))
            if imported:
                self.logger.info("Добавлено рейсов из активных полётов: %s", imported)
                self.reload_data()
            self.render_all()

        def error(_: Exception) -> None:
            self.connected = False

        self.run_task(operation(), "Синхронизация рейсов…", success, error, silent=silent)

    def calculate_times(self) -> None:
        targets = [t for t in self.targets if t.enabled and not t.blacklisted]
        if not targets:
            messagebox.showinfo(APP_NAME, "Нет активных целей")
            return

        endpoint = self.endpoint()
        ship_count = self._safe_int(self.ship_count_var, 25)
        home = self.home()
        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.calculate_times(targets, ship_count, home)

        def success(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                self.db.update_timing(row["coord"], int(row["one"]), int(row["round"]), row.get("gas"))
            self.logger.info("Рассчитаны фактические времена для %s целей", len(rows))
            self.status_var.set(f"Времена рассчитаны · {len(rows)}")
            self.reload_data()

        self.run_task(operation(), "Игра рассчитывает времена…", success)

    def import_from_browser(self) -> None:
        endpoint = self.endpoint()
        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.import_reports()

        def success(reports: list[SpyReport]) -> None:
            inserted, updated = self.db.upsert_reports(reports)
            self.logger.info("Импорт из браузера: %s отчётов, новых %s, обновлено %s", len(reports), inserted, updated)
            self.status_var.set(f"Импортировано: {len(reports)}")
            self.reload_data()
            messagebox.showinfo(APP_NAME, f"Найдено отчётов: {len(reports)}\nНовых целей: {inserted}\nОбновлено: {updated}")

        self.run_task(operation(), "Чтение всех страниц отчётов…", success)

    def collect_combat_history(self) -> None:
        """Read-only import of battle reports; messages are never deleted."""
        endpoint = self.endpoint()
        lookback_hours = self._safe_int(self.report_lookback_var, 24)
        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.collect_combat_reports(lookback_hours=lookback_hours)

        def success(reports) -> None:
            inserted, duplicates, updated = self.db.save_combat_reports(reports)
            self.reload_data()
            self.status_var.set(f"Доклады: +{inserted}, дубли: {duplicates}, целей обновлено: {updated}")
            self.logger.info("Импорт докладов: %s новых, %s дублей", inserted, duplicates)

        self.run_task(operation(), "Доклады: чтение страниц…", success)

    def refresh_spy_reports(self) -> None:
        if not messagebox.askyesno(
            APP_NAME,
            "Обновить разведку в чистом режиме?\n\nБудут удалены только старые шпионские сообщения из раздела «Система» "
            "и очищена локальная история разведок. Остальные системные сообщения не затрагиваются.",
        ):
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Подтвердите необратимое удаление старых шпионских сообщений в Nemexia.\n\n"
            "После очистки программа запросит новые отчёты. Продолжить?",
        ):
            return
        endpoint = self.endpoint()
        async def operation():
            await self.worker.connect(endpoint)
            old_reports = await self.worker.collect_spy_reports()
            deletable_ids = [
                report.message_id for report in old_reports
                if report.message_id and not is_protected_coord(report.coord)
            ]
            deleted = await self.worker.delete_spy_messages(deletable_ids) if deletable_ids else 0
            await self.worker.request_all_spy_reports()
            return deleted, await self.worker.collect_spy_reports()

        def success(payload) -> None:
            deleted, reports = payload
            cleared = self.db.clear_spy_reports()
            inserted, duplicates, updated = self.db.save_spy_reports(reports)
            self.generate_queue()
            self.reload_data()
            self.status_var.set(f"Разведка: удалено {deleted}, локально очищено {cleared}, новых {inserted}")
            self.logger.info("Чистая разведка: удалено=%s, локально=%s, новых=%s, дубли=%s", deleted, cleared, inserted, duplicates)

        self.run_task(operation(), "Разведка: получение и чтение…", success)

    def full_refresh(self) -> None:
        if not messagebox.askyesno(
            APP_NAME,
            "Полное обновление прочитает историю докладов, затем запросит доступные шпионские отчёты и пересоберёт очередь. Сообщения не удаляются. Продолжить?",
        ):
            return
        endpoint = self.endpoint()
        async def operation():
            await self.worker.connect(endpoint)
            battles = await self.worker.collect_combat_reports(
                lookback_hours=self._safe_int(self.report_lookback_var, 24)
            )
            await self.worker.request_all_spy_reports()
            return battles, await self.worker.collect_spy_reports()

        def success(payload) -> None:
            battles, spies = payload
            combat_added, _, _ = self.db.save_combat_reports(battles)
            spy_added, _, _ = self.db.save_spy_reports(spies)
            self.generate_queue()
            self.reload_data()
            self.status_var.set(f"Обновление: доклады +{combat_added}, разведка +{spy_added}")

        self.run_task(operation(), "Полное обновление…", success)

    def import_from_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выбери ZIP или HTML со шпионскими отчётами",
            filetypes=[("Отчёты", "*.zip *.html *.htm"), ("ZIP", "*.zip"), ("HTML", "*.html *.htm")],
            initialdir=self.settings.get("last_import_dir") or str(Path.home()),
        )
        if not paths:
            return
        try:
            reports = parse_report_paths([Path(path) for path in paths])
            inserted, updated = self.db.upsert_reports(reports)
            self.db.set_setting("last_import_dir", str(Path(paths[0]).parent))
            self.logger.info("Импорт из файлов: %s отчётов", len(reports))
            self.reload_data()
            messagebox.showinfo(APP_NAME, f"Найдено отчётов: {len(reports)}\nНовых целей: {inserted}\nОбновлено: {updated}")
        except Exception as exc:
            self.logger.exception("Ошибка импорта файлов")
            messagebox.showerror(APP_NAME, f"Не удалось прочитать отчёты: {exc}")


    # ---------- Asteroids ----------
    def asteroid_home(self) -> tuple[int, int, int]:
        return (
            self._safe_int(self.asteroid_home_g_var, 3),
            self._safe_int(self.asteroid_home_s_var, 39),
            self._safe_int(self.asteroid_home_p_var, 8),
        )

    def _asteroid_options(self) -> dict[str, int | tuple[int, int, int]]:
        start_system = self._safe_int(self.asteroid_start_system_var, 39)
        end_system = self._safe_int(self.asteroid_end_system_var, 1)
        if start_system < end_system:
            raise ValueError("Стартовая система должна быть не меньше конечной")
        return {
            "home": self.asteroid_home(),
            "galaxy": self._safe_int(self.asteroid_galaxy_var, 3),
            "start_system": start_system,
            "end_system": end_system,
            "recycler_count": max(1, self._safe_int(self.asteroid_recyclers_var, 5)),
            "max_flights": max(1, self._safe_int(self.asteroid_max_flights_var, 15)),
            "max_slots": max(1, self._safe_int(self.max_slots_var, 15)),
            "safety_seconds": max(0, self._safe_int(self.asteroid_safety_var, 10)),
        }

    def _asteroid_progress(self, text: str) -> None:
        try:
            self.after(0, self._set_asteroid_progress, text)
        except Exception:
            pass

    def _set_asteroid_progress(self, text: str) -> None:
        self.asteroid_status_var.set(text)
        self.status_var.set(text)

    def _save_asteroid_settings(self) -> None:
        values = {
            "asteroid_home_g": self._safe_int(self.asteroid_home_g_var, 3),
            "asteroid_home_s": self._safe_int(self.asteroid_home_s_var, 39),
            "asteroid_home_p": self._safe_int(self.asteroid_home_p_var, 8),
            "asteroid_galaxy": self._safe_int(self.asteroid_galaxy_var, 3),
            "asteroid_start_system": self._safe_int(self.asteroid_start_system_var, 39),
            "asteroid_end_system": self._safe_int(self.asteroid_end_system_var, 1),
            "asteroid_recyclers": max(1, self._safe_int(self.asteroid_recyclers_var, 5)),
            "asteroid_max_flights": max(1, self._safe_int(self.asteroid_max_flights_var, 15)),
            "asteroid_safety_seconds": max(0, self._safe_int(self.asteroid_safety_var, 10)),
            "asteroid_cycle_buffer_minutes": max(0, self._safe_int(self.asteroid_buffer_var, 5)),
            "asteroid_auto_enabled": bool(self.asteroid_auto_var.get()),
            "asteroid_next_cycle_at": self.asteroid_next_cycle_at.isoformat() if self.asteroid_next_cycle_at else "",
        }
        self.db.set_settings(values)
        self.settings.update(values)

    def scan_asteroids_manual(self) -> None:
        try:
            options = self._asteroid_options()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.asteroid_cancel_event.clear()
        endpoint = self.endpoint()

        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.scan_asteroids(
                home=options["home"], galaxy=int(options["galaxy"]),
                start_system=int(options["start_system"]), end_system=int(options["end_system"]),
                limit=BrowserWorker.asteroid_candidate_limit(int(options["max_flights"])),
                cancelled=self.asteroid_cancel_event.is_set,
                progress=self._asteroid_progress,
            )

        def success(observations: list[AsteroidObservation]) -> None:
            self.asteroid_observations = observations
            self.asteroid_plans = []
            self.asteroid_candidate_var.set(str(len(observations)))
            self.asteroid_ready_var.set("0")
            inserted, duplicates = self.db.save_asteroid_scans(observations)
            self.asteroid_status_var.set(f"Сканирование завершено · найдено {len(observations)}")
            self.status_var.set(f"Астероиды: найдено {len(observations)}")
            self.logger.info("Астероиды: найдено=%s, новых снимков=%s, дублей=%s", len(observations), inserted, duplicates)
            self.render_asteroids()

        def error(exc: Exception) -> None:
            if isinstance(exc, CaptchaRequiredError):
                self._stop_asteroid_auto(str(exc), notify=True)
            self.asteroid_status_var.set(f"Ошибка: {exc}")
            messagebox.showerror(APP_NAME, str(exc))

        self._save_asteroid_settings()
        self.run_task(operation(), "Сканирование астероидов…", success, error)

    def calculate_asteroid_wave(self) -> None:
        observations = list(self.asteroid_observations)
        if not observations:
            messagebox.showinfo(APP_NAME, "Сначала выполни сканирование астероидов")
            return
        try:
            options = self._asteroid_options()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        observations = observations[: BrowserWorker.asteroid_candidate_limit(int(options["max_flights"]))]
        endpoint = self.endpoint()
        self.asteroid_cancel_event.clear()

        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.plan_asteroid_wave(
                observations,
                recycler_count=int(options["recycler_count"]),
                home=options["home"],
                safety_seconds=int(options["safety_seconds"]),
                progress=self._asteroid_progress,
            )

        def success(plans: list[AsteroidPlan]) -> None:
            self.asteroid_plans = plans
            self.asteroid_ready_var.set(str(len(plans)))
            self.asteroid_status_var.set(f"Волна рассчитана · {len(plans)} рейсов")
            self.status_var.set(f"Рассчитано астероидных рейсов: {len(plans)}")
            self.logger.info("Рассчитана астероидная волна: %s", len(plans))
            self.render_asteroids()

        def error(exc: Exception) -> None:
            if isinstance(exc, CaptchaRequiredError):
                self._stop_asteroid_auto(str(exc), notify=True)
            self.asteroid_status_var.set(f"Ошибка: {exc}")
            messagebox.showerror(APP_NAME, str(exc))

        self._save_asteroid_settings()
        self.run_task(operation(), "Расчёт астероидной волны…", success, error)

    def send_asteroid_wave(self) -> None:
        try:
            options = self._asteroid_options()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Сканировать системы {options['start_system']}…{options['end_system']} и отправить до "
            f"{options['max_flights']} рейсов?\n\nПо {options['recycler_count']} переработчиков, миссия «Добыча газа».\n"
            "Каждый рейс будет заново рассчитан непосредственно перед отправкой.",
        ):
            return
        self._run_asteroid_cycle(auto=False)

    def toggle_asteroid_auto(self) -> None:
        if self.asteroid_auto_var.get():
            self._stop_asteroid_auto("Автопродление остановлено пользователем", notify=False)
            return
        try:
            options = self._asteroid_options()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        ok = messagebox.askyesno(
            APP_NAME,
            "Включить автопродление астероидных рейсов?\n\n"
            f"Программа будет отправлять до {options['max_flights']} рейсов по "
            f"{options['recycler_count']} переработчиков, ждать возврата последнего флота и ещё "
            f"{self._safe_int(self.asteroid_buffer_var, 5)} мин., затем повторять цикл.\n\n"
            "При CAPTCHA, неподтверждённой отправке или любой серьёзной ошибке автоматизация остановится.",
        )
        if not ok:
            return
        # Two independent auto senders must never compete for the same browser and fleet slots.
        if self.auto_var.get():
            self.auto_var.set(False)
            self.db.set_setting("auto_enabled", False)
            self.logger.info("Обычная автоотправка отключена при запуске астероидного автопродления")
        self.asteroid_auto_var.set(True)
        self.asteroid_next_cycle_at = None
        self.asteroid_cancel_event.clear()
        self._save_asteroid_settings()
        self.asteroid_status_var.set("Автопродление включено · запуск первого цикла")
        self.logger.info("Астероиды: автопродление включено")
        self.render_all()
        self._run_asteroid_cycle(auto=True)

    def cancel_asteroid_operation(self) -> None:
        self.asteroid_cancel_event.set()
        if self.asteroid_auto_var.get():
            self._stop_asteroid_auto("Операция и автопродление остановлены пользователем", notify=False)
        else:
            self.asteroid_status_var.set("Остановка запрошена…")
            self.status_var.set("Остановка астероидной операции…")

    def _stop_asteroid_auto(self, reason: str, *, notify: bool) -> None:
        was_enabled = bool(self.asteroid_auto_var.get())
        self.asteroid_auto_var.set(False)
        self.asteroid_next_cycle_at = None
        self.db.set_settings({"asteroid_auto_enabled": False, "asteroid_next_cycle_at": ""})
        self.settings.update({"asteroid_auto_enabled": False, "asteroid_next_cycle_at": ""})
        self.asteroid_status_var.set(reason)
        self.asteroid_next_var.set("—")
        if was_enabled:
            self.logger.warning("Астероиды: автопродление остановлено: %s", reason)
            if notify:
                self.tray.notify("Астероидное автопродление остановлено", reason)
        self.render_all()

    def _schedule_next_asteroid_cycle(self, results: list[dict[str, Any]]) -> datetime | None:
        return_times = [parse_dt(str(row.get("return_at") or "")) for row in results]
        return_times = [value for value in return_times if value is not None]
        if not return_times:
            return None
        next_cycle = max(return_times) + timedelta(minutes=max(0, self._safe_int(self.asteroid_buffer_var, 5)))
        self.asteroid_next_cycle_at = next_cycle
        self.db.set_settings({
            "asteroid_auto_enabled": bool(self.asteroid_auto_var.get()),
            "asteroid_next_cycle_at": next_cycle.isoformat(),
        })
        self.settings.update({"asteroid_next_cycle_at": next_cycle.isoformat()})
        return next_cycle

    def _run_asteroid_cycle(self, *, auto: bool) -> None:
        if self.busy:
            if not auto:
                messagebox.showinfo(APP_NAME, "Дождись завершения текущей операции")
            return
        try:
            options = self._asteroid_options()
        except ValueError as exc:
            if auto:
                self._stop_asteroid_auto(str(exc), notify=True)
            else:
                messagebox.showerror(APP_NAME, str(exc))
            return
        self.asteroid_cancel_event.clear()
        cycle_id = self.db.start_asteroid_cycle(int(options["max_flights"]))
        endpoint = self.endpoint()

        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.run_asteroid_cycle(
                home=options["home"], galaxy=int(options["galaxy"]),
                start_system=int(options["start_system"]), end_system=int(options["end_system"]),
                recycler_count=int(options["recycler_count"]), max_flights=int(options["max_flights"]),
                max_slots=int(options["max_slots"]), safety_seconds=int(options["safety_seconds"]),
                cancelled=self.asteroid_cancel_event.is_set, progress=self._asteroid_progress,
            )

        def success(payload: dict[str, Any]) -> None:
            observations = list(payload.get("observations") or [])
            results = list(payload.get("results") or [])
            error_text = str(payload.get("error") or "").strip() or None
            error_kind = str(payload.get("error_kind") or "").strip() or None
            self.asteroid_observations = observations
            self.asteroid_plans = []
            self.asteroid_candidate_var.set(str(payload.get("candidates", len(observations))))
            self.asteroid_ready_var.set(str(payload.get("ready", len(results))))
            self.db.save_asteroid_scans(observations)
            for result in results:
                verified = bool(result.get("verified", True))
                self.db.add_asteroid_flight(
                    result,
                    cycle_id=cycle_id,
                    status="sent" if verified else "unverified",
                    error=None if verified else (error_text or "Отправка не подтверждена таблицей полётов"),
                )
            sent = sum(1 for result in results if bool(result.get("verified", True)))
            next_cycle: datetime | None = None
            cycle_status = "completed"
            if error_text:
                cycle_status = "stopped" if sent else "failed"
            elif auto and results:
                next_cycle = self._schedule_next_asteroid_cycle(results)
                if next_cycle is None:
                    error_text = "Не удалось определить возврат последнего рейса"
                    error_kind = "timing"
                    cycle_status = "failed"
            self.db.finish_asteroid_cycle(
                cycle_id,
                found=len(observations), sent=sent, status=cycle_status,
                error=error_text, next_cycle_at=next_cycle.isoformat() if next_cycle else None,
            )
            self.asteroid_sent_var.set(str(sent))
            self.render_asteroids()
            if error_text:
                self.asteroid_status_var.set(f"Цикл остановлен: {error_text}")
                if auto:
                    self._stop_asteroid_auto(error_text, notify=True)
                else:
                    messagebox.showerror(APP_NAME, f"Отправлено: {sent}\nОстановка:\n{error_text}")
                return
            if auto:
                if next_cycle:
                    local_text = next_cycle.astimezone().strftime("%d.%m.%Y %H:%M:%S") if next_cycle.tzinfo else next_cycle.strftime("%d.%m.%Y %H:%M:%S")
                    self.asteroid_status_var.set(f"Цикл завершён · следующий запуск {local_text}")
                    self.logger.info("Астероиды: отправлено=%s, следующий цикл=%s", sent, local_text)
                elif not results:
                    self._stop_asteroid_auto("Цикл не создал ни одного рейса", notify=True)
            else:
                self.asteroid_status_var.set(f"Волна отправлена · {sent} рейсов")
                self.status_var.set(f"Астероиды: отправлено {sent}")
                messagebox.showinfo(APP_NAME, f"Отправлено астероидных рейсов: {sent}")
            self.render_all()

        def error(exc: Exception) -> None:
            self.db.finish_asteroid_cycle(
                cycle_id, found=0, sent=0, status="failed", error=str(exc), next_cycle_at=None
            )
            self.asteroid_status_var.set(f"Ошибка: {exc}")
            if auto or isinstance(exc, CaptchaRequiredError):
                self._stop_asteroid_auto(str(exc), notify=True)
            else:
                messagebox.showerror(APP_NAME, str(exc))

        self._save_asteroid_settings()
        self.run_task(
            operation(),
            "Астероиды: сканирование и отправка…",
            success,
            error,
            silent=auto,
        )

    def _check_asteroid_captcha(self) -> None:
        if self._asteroid_captcha_inflight or self.busy or not self.asteroid_auto_var.get():
            return
        self._asteroid_captcha_inflight = True
        future = self.worker.submit(self.worker.captcha_present())

        def poll() -> None:
            if not future.done():
                self.after(100, poll)
                return
            self._asteroid_captcha_inflight = False
            try:
                present = bool(future.result())
            except Exception:
                present = False
            if present and self.asteroid_auto_var.get():
                self._stop_asteroid_auto(
                    "Nemexia запросила подтверждение человека. Пройди CAPTCHA вручную и включи автопродление снова.",
                    notify=True,
                )

        self.after(100, poll)

    # ---------- Queue and sending ----------
    def generate_queue(self) -> None:
        count = max(1, self._safe_int(self.queue_size_var, 45))
        coords = [target.coord for target, _ in self.ranked_targets()[:count]]
        self.db.replace_queue(coords)
        minimum_metal = max(0, self._safe_int(self.min_metal_queue_var, 480000))
        self.db.set_settings({"queue_size": count, "min_metal_for_queue": minimum_metal})
        self.settings.update({"queue_size": count, "min_metal_for_queue": minimum_metal})
        self.logger.info("Сформирован план отправки: %s целей, металл от %s", len(coords), minimum_metal)
        self.render_all()

    def _selected_queue_items(self) -> list[QueueItem]:
        selected_ids = []
        for iid in self.queue_tree.selection():
            try:
                selected_ids.append(int(iid.split(":", 1)[1]))
            except Exception:
                continue
        by_id = {item.id: item for item in self.db.list_queue()}
        return [by_id[item_id] for item_id in selected_ids if item_id in by_id]

    def _checked_queue_items(self) -> list[QueueItem]:
        return [item for item in self.db.list_queue() if item.id in self.checked_queue_ids]

    def _queue_target_pairs(self, items: list[QueueItem]) -> list[tuple[QueueItem, Target]]:
        """Keep a queue row coupled to its own target if a stale row is encountered."""
        return [
            (item, target) for item in items
            if (target := self.target_by_coord.get(item.coord)) and target.enabled and not target.blacklisted
        ]

    def _toggle_queue_checkbox(self, event: tk.Event) -> str | None:
        """Toggle only the explicit wave checkbox; ordinary row clicks stay harmless."""
        if self.queue_tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.queue_tree.identify_column(event.x) != "#1":
            return None
        iid = self.queue_tree.identify_row(event.y)
        if not iid.startswith("q:"):
            return "break"
        try:
            item_id = int(iid.split(":", 1)[1])
        except ValueError:
            return "break"
        item = next((row for row in self.db.list_queue() if row.id == item_id), None)
        if item is None or item.state != "queued":
            return "break"
        if item_id in self.checked_queue_ids:
            self.checked_queue_ids.remove(item_id)
        else:
            self.checked_queue_ids.add(item_id)
        values = list(self.queue_tree.item(iid, "values"))
        if values:
            values[0] = "☑" if item_id in self.checked_queue_ids else "☐"
            self.queue_tree.item(iid, values=values)
        return "break"

    def reset_stuck_sending(self) -> None:
        """Use the browser's current active flights before changing any sending status."""
        endpoint = self.endpoint()

        async def operation() -> list[Flight]:
            await self.worker.connect(endpoint)
            return await self.worker.sync_flights()

        def success(flights: list[Flight]) -> None:
            self.active_flights = flights
            restored = self.db.reset_stuck_sending(self._active_coords())
            self.render_all()
            if restored:
                self.status_var.set(f"Возвращено в план: {len(restored)}")
                messagebox.showinfo(APP_NAME, f"Возвращено в «Готов»: {len(restored)}.\nПроверены активные рейсы в игре: {len(flights)}.")
            else:
                messagebox.showinfo(APP_NAME, f"Зависших статусов нет. Активных рейсов в игре: {len(flights)}.")

        self.run_task(operation(), "Проверка активных рейсов…", success)

    def send_next(self) -> None:
        queue = [item for item in self.db.list_queue() if item.state == "queued"]
        if not queue:
            messagebox.showinfo(APP_NAME, "Очередь пуста. Сначала сформируй её.")
            return
        active = self._active_coords()
        item = next(
            (q for q in queue if q.coord not in active
             and (target := self.target_by_coord.get(q.coord)) and target.enabled and not target.blacklisted),
            None,
        )
        if item is None:
            messagebox.showinfo(APP_NAME, "Все цели очереди уже атакуются")
            return
        target = self.target_by_coord.get(item.coord)
        if target:
            self._send_items([item], [target], confirm=self.confirm_single_var.get())

    def send_selected_dashboard(self) -> None:
        selected = self.dashboard_tree.selection()
        if not selected:
            return
        coord = selected[0].split(":", 1)[1]
        target = self.target_by_coord.get(coord)
        if not target:
            return
        existing = next((q for q in self.db.list_queue() if q.coord == coord and q.state == "queued"), None)
        if existing is None:
            self.db.add_queue([coord])
            existing = next((q for q in self.db.list_queue() if q.coord == coord and q.state == "queued"), None)
        if existing:
            self._send_items([existing], [target], confirm=self.confirm_single_var.get())

    def send_wave(self) -> None:
        active_count = len(self.active_flights)
        free = max(0, self._safe_int(self.max_slots_var, 15) - active_count)
        if free <= 0:
            messagebox.showinfo(APP_NAME, "Свободных слотов нет")
            return
        active = self._active_coords()
        selected = [item for item in self._checked_queue_items() if item.state == "queued" and item.coord not in active]
        if not selected:
            messagebox.showinfo(APP_NAME, "Отметь галочками цели для волны. Для отправки по приоритету используй «Отправить следующий».")
            return
        pairs = self._queue_target_pairs(selected[:free])
        if not pairs:
            messagebox.showinfo(APP_NAME, "В очереди нет доступных целей")
            return
        items = [item for item, _ in pairs]
        targets = [target for _, target in pairs]
        self._send_items(items, targets, confirm=self.confirm_wave_var.get(), wave=True)

    def _send_items(self, items: list[QueueItem], targets: list[Target], confirm: bool, wave: bool = False) -> None:
        ship_count = self._safe_int(self.ship_count_var, 25)
        if confirm:
            preview = "\n".join(f"{index + 1}. {target.coord} — {target.player}" for index, target in enumerate(targets[:15]))
            extra = "" if len(targets) <= 15 else f"\n…ещё {len(targets) - 15}"
            if not messagebox.askyesno(
                APP_NAME,
                f"Отправить {'волну' if wave else 'рейс'}: {len(targets)} шт.?\n"
                f"По {ship_count} мегатранспортировщиков.\n\n{preview}{extra}",
            ):
                return
        for item in items:
            self.db.set_queue_state(item.id, "sending")
        self.render_queue()

        endpoint = self.endpoint()
        max_slots = self._safe_int(self.max_slots_var, 15)
        home = self.home()
        async def operation():
            await self.worker.connect(endpoint)
            synced = await self.worker.sync_flights()
            free = max(0, max_slots - len(synced))
            results: list[tuple[int, dict[str, Any] | None, str | None]] = []
            for item, target in list(zip(items, targets))[:free]:
                try:
                    result = await self.worker.send_raid(target, ship_count, home)
                    results.append((item.id, result, None))
                except Exception as exc:
                    results.append((item.id, None, str(exc)))
                    break
            return synced, results

        def success(payload: tuple[list[Flight], list[tuple[int, dict[str, Any] | None, str | None]]]) -> None:
            synced, results = payload
            self.active_flights = synced
            sent = 0
            errors = []
            processed_ids = set()
            for item_id, result, error in results:
                processed_ids.add(item_id)
                if result:
                    self.db.add_history(result, "sent")
                    self.db.set_queue_state(item_id, "done")
                    self.db.update_timing(result["target"], result["one_way_seconds"], result["round_trip_seconds"], result.get("gas_needed"))
                    sent += 1
                    self.logger.info("Отправлено %s МТ → %s; fleet_id=%s", ship_count, result["target"], result.get("fleet_id"))
                else:
                    self.db.set_queue_state(item_id, "failed")
                    target = next((t for i, t in zip(items, targets) if i.id == item_id), None)
                    failure = {"target": target.coord if target else "—", "player": target.player if target else "—",
                               "ship_count": ship_count, "sent_at": utc_now().isoformat()}
                    self.db.add_history(failure, "failed", error)
                    errors.append(error or "Неизвестная ошибка")
                    self.logger.error("Ошибка отправки: %s", error)
            for item in items:
                if item.id not in processed_ids:
                    self.db.set_queue_state(item.id, "queued")
            self.reload_data()
            self.sync_flights(silent=True)
            self.status_var.set(f"Отправлено рейсов: {sent}")
            if errors:
                messagebox.showerror(APP_NAME, f"Отправлено: {sent}\nОстановка на ошибке:\n{errors[0]}")
            elif not wave:
                messagebox.showinfo(APP_NAME, "Рейс отправлен и подтверждён таблицей полётов")

        def error(exc: Exception) -> None:
            for item in items:
                self.db.set_queue_state(item.id, "queued")
            self.render_queue()
            messagebox.showerror(APP_NAME, str(exc))

        self.run_task(operation(), f"Отправка рейсов: {len(targets)}…", success, error)

    def prepare_selected_queue(self) -> None:
        selected = self._selected_queue_items()
        if not selected:
            selected = [item for item in self.db.list_queue() if item.state == "queued"][:1]
        if not selected:
            messagebox.showinfo(APP_NAME, "Очередь пуста")
            return
        target = self.target_by_coord.get(selected[0].coord)
        if not target:
            return

        endpoint = self.endpoint()
        ship_count = self._safe_int(self.ship_count_var, 25)
        home = self.home()
        async def operation():
            await self.worker.connect(endpoint)
            return await self.worker.prepare_raid(target, ship_count, home)

        def success(result: dict[str, Any]) -> None:
            self.status_var.set(f"Подготовлено: {target.coord}")
            self.logger.info("Подготовлен рейс на %s без отправки", target.coord)
            messagebox.showinfo(APP_NAME, f"Рейс на {target.coord} заполнен в браузере.\nПоследнее нажатие «Отправить» — вручную.")

        self.run_task(operation(), f"Подготовка {target.coord}…", success)

    def move_queue(self, direction: int) -> None:
        selected = self._selected_queue_items()
        if len(selected) != 1:
            messagebox.showinfo(APP_NAME, "Выбери одну строку")
            return
        self.db.move_queue_item(selected[0].id, direction)
        self.render_queue()

    def remove_queue_selected(self) -> None:
        selected = self._selected_queue_items()
        for item in selected:
            self.db.remove_queue_item(item.id)
        self.render_all()

    def clear_queue(self) -> None:
        if messagebox.askyesno(APP_NAME, "Очистить очередь?"):
            self.db.clear_queue()
            self.render_all()

    # ---------- Targets ----------
    def add_target(self) -> None:
        dialog = TargetDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        data = dialog.result
        self.db.add_target(data["coord"], data["player"], data["energy"])
        self.db.update_target_flags(data["coord"], enabled=data["enabled"], blacklisted=data["blacklisted"], notes=data["notes"])
        self.reload_data()

    def _selected_target_coords(self) -> list[str]:
        coords = []
        for iid in self.targets_tree.selection():
            if iid.startswith("t:"):
                coords.append(iid[2:])
        return coords

    def edit_target(self) -> None:
        coords = self._selected_target_coords()
        if len(coords) != 1:
            messagebox.showinfo(APP_NAME, "Выбери одну цель")
            return
        target = self.target_by_coord[coords[0]]
        dialog = TargetDialog(self, target)
        self.wait_window(dialog)
        if not dialog.result:
            return
        data = dialog.result
        if data["coord"] != target.coord:
            self.db.delete_target(target.coord)
        self.db.add_target(data["coord"], data["player"], data["energy"])
        self.db.update_target_flags(data["coord"], enabled=data["enabled"], blacklisted=data["blacklisted"], notes=data["notes"])
        self.reload_data()

    def delete_target(self) -> None:
        coords = self._selected_target_coords()
        if not coords:
            return
        if not messagebox.askyesno(APP_NAME, f"Удалить целей: {len(coords)}?"):
            return
        for coord in coords:
            self.db.delete_target(coord)
        self.reload_data()

    # ---------- Settings, export, logs ----------
    def save_settings(self) -> None:
        values = {
            "port": self._safe_int(self.port_var, 9222), "ship_count": self._safe_int(self.ship_count_var, 25),
            "min_energy": self._safe_int(self.min_energy_var, 7000),
            "min_metal_for_queue": max(0, self._safe_int(self.min_metal_queue_var, 480000)),
            "queue_size": self._safe_int(self.queue_size_var, 45),
            "max_slots": self._safe_int(self.max_slots_var, 15), "home_g": self._safe_int(self.home_g_var, 3),
            "home_s": self._safe_int(self.home_s_var, 39), "home_p": self._safe_int(self.home_p_var, 11),
            "repeat_minutes": self._safe_int(self.repeat_minutes_var, 60),
            "report_lookback_hours": self._safe_int(self.report_lookback_var, 24),
            "auto_enabled": bool(self.auto_var.get()), "auto_interval_seconds": self._safe_int(self.auto_interval_var, 30),
            "minimize_to_tray": bool(self.tray_var.get()), "notify_returns": bool(self.notify_var.get()),
            "confirm_single": bool(self.confirm_single_var.get()), "confirm_wave": bool(self.confirm_wave_var.get()),
            "asteroid_home_g": self._safe_int(self.asteroid_home_g_var, 3),
            "asteroid_home_s": self._safe_int(self.asteroid_home_s_var, 39),
            "asteroid_home_p": self._safe_int(self.asteroid_home_p_var, 8),
            "asteroid_galaxy": self._safe_int(self.asteroid_galaxy_var, 3),
            "asteroid_start_system": self._safe_int(self.asteroid_start_system_var, 39),
            "asteroid_end_system": self._safe_int(self.asteroid_end_system_var, 1),
            "asteroid_recyclers": max(1, self._safe_int(self.asteroid_recyclers_var, 5)),
            "asteroid_max_flights": max(1, self._safe_int(self.asteroid_max_flights_var, 15)),
            "asteroid_safety_seconds": max(0, self._safe_int(self.asteroid_safety_var, 10)),
            "asteroid_cycle_buffer_minutes": max(0, self._safe_int(self.asteroid_buffer_var, 5)),
            "asteroid_auto_enabled": bool(self.asteroid_auto_var.get()),
            "asteroid_next_cycle_at": self.asteroid_next_cycle_at.isoformat() if self.asteroid_next_cycle_at else "",
        }
        self.db.set_settings(values)
        self.settings.update(values)
        self.logger.info("Настройки сохранены")
        self.render_all()
        messagebox.showinfo(APP_NAME, "Настройки сохранены")

    def toggle_auto(self) -> None:
        if self.auto_var.get():
            ok = messagebox.askyesno(
                APP_NAME,
                "Включить автоотправку?\n\nПрограмма будет отправлять волну из целей очереди по числу свободных слотов. "
                "При первой ошибке режим автоматически отключится.",
            )
            if not ok:
                self.auto_var.set(False)
            else:
                if self.asteroid_auto_var.get():
                    self._stop_asteroid_auto("Астероидное автопродление отключено при запуске обычной автоотправки", notify=False)
        self.db.set_setting("auto_enabled", bool(self.auto_var.get()))
        self.render_all()

    def manual_backup(self) -> None:
        try:
            path = self.db.backup(BACKUP_DIR)
            messagebox.showinfo(APP_NAME, f"Резервная копия создана:\n{path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def export_history(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Экспорт истории", defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"nemexia_history_{datetime.now().strftime('%Y%m%d')}.csv",
        )
        if not path:
            return
        rows = self.db.list_history(100000)
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["Отправлен", "Цель", "Игрок", "МТ", "Прибытие", "Возврат", "Fleet ID", "Статус", "Ошибка"])
            for row in rows:
                writer.writerow([row["sent_at"], row["target"], row["player"], row["ship_count"], row["arrival_at"],
                                 row["return_at"], row["fleet_id"], row["status"], row["error"]])
        self.logger.info("История экспортирована: %s", path)

    def open_data_dir(self) -> None:
        self._open_folder(DATA_DIR)

    def show_build_info(self) -> None:
        messagebox.showinfo(
            APP_NAME,
            "Запусти build_exe.bat из папки программы.\n"
            "Готовый файл появится в dist\\NemexiaRaidManager.exe.\n\n"
            "Сборка выполняется на Windows, потому что PyInstaller не создаёт Windows EXE из Linux.",
        )

    @staticmethod
    def _open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _append_log_threadsafe(self, line: str) -> None:
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-2000:]
        if hasattr(self, "log_text"):
            try:
                self.after(0, self._append_log_ui, line)
            except Exception:
                pass

    def _append_log_ui(self, line: str) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log_view(self) -> None:
        self.log_lines.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ---------- Timers, health, auto ----------
    def _tick(self) -> None:
        if self._closing:
            return
        now = utc_now()
        valid: list[Flight] = []
        for flight in self.active_flights:
            key = flight.fleet_id or f"{flight.target}:{flight.return_at.isoformat() if flight.return_at else ''}"
            if flight.return_at and flight.return_at <= now:
                if key not in self.notified_returns:
                    self.notified_returns.add(key)
                    if self.notify_var.get():
                        self.tray.notify("Флот вернулся", f"Освободился слот после рейса на {flight.target}")
                        self.logger.info("Флот вернулся с %s", flight.target)
                continue
            valid.append(flight)
        if len(valid) != len(self.active_flights):
            self.active_flights = valid
        self.render_dashboard()
        self.render_active()

        monotonic = time.monotonic()
        if monotonic - self._health_last >= 20 and not self.busy:
            self._health_last = monotonic
            if cdp_is_available(self._safe_int(self.port_var, 9222)) and not self.connected:
                self.connect_browser(silent=True)
        if self.asteroid_next_cycle_at:
            next_at = self.asteroid_next_cycle_at
            compare_now = now
            if next_at.tzinfo is None:
                compare_now = datetime.now()
            self.asteroid_next_var.set(remaining(next_at, compare_now))
        else:
            self.asteroid_next_var.set("—")

        if self.asteroid_auto_var.get():
            if monotonic - self._asteroid_captcha_last >= 20:
                self._asteroid_captcha_last = monotonic
                self._check_asteroid_captcha()
            due = self.asteroid_next_cycle_at is None
            if self.asteroid_next_cycle_at is not None:
                next_at = self.asteroid_next_cycle_at
                compare_now = now if next_at.tzinfo is not None else datetime.now()
                due = next_at <= compare_now
            if due and not self.busy:
                self._run_asteroid_cycle(auto=True)

        if (self.auto_var.get() and not self.asteroid_auto_var.get() and not self.busy
                and monotonic - self._auto_last >= max(10, self._safe_int(self.auto_interval_var, 30))):
            self._auto_last = monotonic
            self._auto_cycle()
        self.after(1000, self._tick)

    def _auto_cycle(self) -> None:
        queue = [item for item in self.db.list_queue() if item.state == "queued"]
        if not queue:
            return

        endpoint = self.endpoint()
        max_slots = self._safe_int(self.max_slots_var, 15)
        ship_count = self._safe_int(self.ship_count_var, 25)
        home = self.home()
        async def operation():
            await self.worker.connect(endpoint)
            flights = await self.worker.sync_flights()
            free = max(0, max_slots - len(flights))
            if free <= 0:
                return flights, []
            active = {f.target.replace(" ", "") for f in flights}
            candidates = [item for item in queue if item.coord not in active][:free]
            results: list[tuple[int, dict[str, Any] | None, str | None]] = []
            for item in candidates:
                target = self.target_by_coord.get(item.coord)
                if target is None or not target.enabled or target.blacklisted:
                    results.append((item.id, None, "Цель исключена или отсутствует в базе"))
                    break
                try:
                    results.append((item.id, await self.worker.send_raid(target, ship_count, home), None))
                except Exception as exc:
                    results.append((item.id, None, str(exc)))
                    break
            return flights, results

        def success(payload: tuple[list[Flight], list[tuple[int, dict[str, Any] | None, str | None]]]) -> None:
            flights, results = payload
            self.active_flights = flights
            if not results:
                self.render_all()
                return
            sent = 0
            error_text: str | None = None
            for item_id, result, error_text in results:
                if result:
                    self.db.add_history(result, "sent")
                    self.db.set_queue_state(item_id, "done")
                    self.db.update_timing(result["target"], result["one_way_seconds"], result["round_trip_seconds"], result.get("gas_needed"))
                    sent += 1
                    self.logger.info("Авто: отправлен рейс на %s", result["target"])
                else:
                    self.db.set_queue_state(item_id, "failed")
                    break
            if error_text:
                self.auto_var.set(False)
                self.db.set_setting("auto_enabled", False)
                self.logger.error("Авто остановлено: %s", error_text)
                self.tray.notify("Автоотправка остановлена", error_text)
            if sent:
                self.logger.info("Авто: отправлена волна из %s рейсов", sent)
                self.reload_data()
                self.sync_flights(silent=True)
            else:
                self.render_all()

        def error(exc: Exception) -> None:
            self.auto_var.set(False)
            self.db.set_setting("auto_enabled", False)
            self.logger.error("Авто остановлено: %s", exc)
            self.render_all()

        self.run_task(operation(), "Авто: проверка слотов…", success, error, silent=True)

    # ---------- Window lifecycle ----------
    def on_close(self) -> None:
        self.save_settings_silent()
        if self.tray_var.get() and self.tray.available:
            self.withdraw()
            self.tray.start()
            self.tray.notify(APP_NAME, "Программа продолжает следить за таймерами")
        else:
            self.exit_app()

    def restore_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def save_settings_silent(self) -> None:
        values = {
            "port": self._safe_int(self.port_var, 9222), "ship_count": self._safe_int(self.ship_count_var, 25),
            "min_energy": self._safe_int(self.min_energy_var, 7000),
            "min_metal_for_queue": max(0, self._safe_int(self.min_metal_queue_var, 480000)),
            "queue_size": self._safe_int(self.queue_size_var, 45),
            "max_slots": self._safe_int(self.max_slots_var, 15), "home_g": self._safe_int(self.home_g_var, 3),
            "home_s": self._safe_int(self.home_s_var, 39), "home_p": self._safe_int(self.home_p_var, 11),
            "repeat_minutes": self._safe_int(self.repeat_minutes_var, 60),
            "report_lookback_hours": self._safe_int(self.report_lookback_var, 24),
            "auto_enabled": bool(self.auto_var.get()), "auto_interval_seconds": self._safe_int(self.auto_interval_var, 30),
            "minimize_to_tray": bool(self.tray_var.get()), "notify_returns": bool(self.notify_var.get()),
            "confirm_single": bool(self.confirm_single_var.get()), "confirm_wave": bool(self.confirm_wave_var.get()),
            "asteroid_home_g": self._safe_int(self.asteroid_home_g_var, 3),
            "asteroid_home_s": self._safe_int(self.asteroid_home_s_var, 39),
            "asteroid_home_p": self._safe_int(self.asteroid_home_p_var, 8),
            "asteroid_galaxy": self._safe_int(self.asteroid_galaxy_var, 3),
            "asteroid_start_system": self._safe_int(self.asteroid_start_system_var, 39),
            "asteroid_end_system": self._safe_int(self.asteroid_end_system_var, 1),
            "asteroid_recyclers": max(1, self._safe_int(self.asteroid_recyclers_var, 5)),
            "asteroid_max_flights": max(1, self._safe_int(self.asteroid_max_flights_var, 15)),
            "asteroid_safety_seconds": max(0, self._safe_int(self.asteroid_safety_var, 10)),
            "asteroid_cycle_buffer_minutes": max(0, self._safe_int(self.asteroid_buffer_var, 5)),
            "asteroid_auto_enabled": bool(self.asteroid_auto_var.get()),
            "asteroid_next_cycle_at": self.asteroid_next_cycle_at.isoformat() if self.asteroid_next_cycle_at else "",
        }
        self.db.set_settings(values)

    def exit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.save_settings_silent()
        self.tray.stop()
        try:
            self.db.backup(BACKUP_DIR)
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = RaidManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
