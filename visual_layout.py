from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk

from visual_system import (
    ACCENT,
    BORDER_1,
    ERROR_BG,
    FONT_BODY,
    FONT_BODY_STRONG,
    FONT_CAPTION,
    FONT_DISPLAY,
    FONT_PAGE_TITLE,
    INFO_BG,
    LOG_BG,
    LOG_TEXT,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    SUCCESS_BG,
    SURFACE_0,
    SURFACE_1,
    SURFACE_2,
    SURFACE_3,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    make_button,
)


_INSTALLED_CLASSES: set[type[Any]] = set()


def _control_group(parent: tk.Misc, title: str) -> tuple[tk.Frame, tk.Frame]:
    card = tk.Frame(parent, bg=SURFACE_2, highlightbackground=BORDER_1, highlightthickness=1)
    tk.Label(
        card,
        text=title,
        bg=SURFACE_2,
        fg=TEXT_3,
        font=FONT_CAPTION,
        anchor="w",
    ).pack(fill="x", padx=SPACE_MD, pady=(SPACE_MD, SPACE_SM))
    body = tk.Frame(card, bg=SURFACE_2, padx=SPACE_MD, pady=(0, SPACE_MD))
    body.pack(fill="both", expand=True)
    return card, body


def _spin_field(
    app: Any,
    parent: tk.Misc,
    label: str,
    variable: tk.Variable,
    start: int,
    end: int,
    width: int = 7,
) -> tk.Frame:
    block = tk.Frame(parent, bg=SURFACE_2)
    app.make_field_label(block, label).pack(anchor="w")
    app.make_spinbox(block, variable, from_=start, to=end, width=width).pack(
        anchor="w", pady=(SPACE_SM, 0), ipady=4
    )
    return block


def _nav_item(app: Any, parent: tk.Misc, key: str, label: str) -> tk.Button:
    row = tk.Frame(parent, bg=SURFACE_1)
    row.pack(fill="x", padx=SPACE_SM, pady=2)
    rail = tk.Frame(row, bg=SURFACE_1, width=3)
    rail.pack(side="left", fill="y")
    rail.pack_propagate(False)
    button = tk.Button(
        row,
        text=label,
        anchor="w",
        command=lambda k=key: app.show_page(k),
        bg=SURFACE_1,
        fg=TEXT_2,
        activebackground=SURFACE_3,
        activeforeground=TEXT_1,
        relief="flat",
        bd=0,
        padx=SPACE_MD,
        pady=9,
        cursor="hand2",
        highlightthickness=0,
        font=FONT_BODY_STRONG,
    )
    button.pack(side="left", fill="x", expand=True)
    setattr(button, "_nav_rail", rail)
    app.nav_buttons[key] = button
    return button


def _nav_group(app: Any, sidebar: tk.Misc, title: str, items: tuple[tuple[str, str], ...]) -> tk.Frame:
    group = tk.Frame(sidebar, bg=SURFACE_1)
    group.pack(fill="x", pady=(SPACE_SM, 0))
    tk.Label(
        group,
        text=title,
        bg=SURFACE_1,
        fg=TEXT_3,
        font=FONT_CAPTION,
        anchor="w",
    ).pack(fill="x", padx=SPACE_LG, pady=(0, SPACE_XS if 'SPACE_XS' in globals() else 4))
    for key, label in items:
        _nav_item(app, group, key, label)
    return group


def _apply_semantic_tags(app: Any) -> None:
    if hasattr(app, "queue_tree"):
        app.queue_tree.tag_configure("active", background=SUCCESS_BG)
        app.queue_tree.tag_configure("sending", background=INFO_BG)
        app.queue_tree.tag_configure("failed", background=ERROR_BG)
        app.queue_tree.tag_configure("sent", foreground=TEXT_3)
    if hasattr(app, "asteroid_tree"):
        app.asteroid_tree.tag_configure("ready", background=SUCCESS_BG)
        app.asteroid_tree.tag_configure("sent", foreground=SUCCESS)
        app.asteroid_tree.tag_configure("error", background=ERROR_BG)
    if hasattr(app, "targets_tree"):
        app.targets_tree.tag_configure("active", background=SUCCESS_BG)
        app.targets_tree.tag_configure("black", foreground=TEXT_3)
        app.targets_tree.tag_configure("disabled", foreground=TEXT_3)
    if hasattr(app, "debris_tree"):
        app.debris_tree.tag_configure("sent", background=SUCCESS_BG)
        app.debris_tree.tag_configure("error", background=ERROR_BG)
    if hasattr(app, "log_text"):
        app.log_text.configure(bg=LOG_BG, fg=LOG_TEXT, insertbackground=TEXT_1)


def install_visual_layout(app_class: type[Any]) -> None:
    if app_class in _INSTALLED_CLASSES:
        return

    def build_shell(self: Any) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            self,
            bg=SURFACE_1,
            width=220,
            highlightbackground=BORDER_1,
            highlightthickness=1,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        logo = tk.Frame(sidebar, bg=SURFACE_1, padx=SPACE_LG, pady=SPACE_XL)
        logo.pack(fill="x")
        tk.Label(logo, text="NEMEXIA", bg=SURFACE_1, fg=TEXT_1, font=FONT_DISPLAY).pack(anchor="w")
        tk.Label(logo, text="RAID MANAGER", bg=SURFACE_1, fg=ACCENT, font=FONT_CAPTION).pack(
            anchor="w", pady=(4, 0)
        )

        self._nav_group_frames = {
            "overview": _nav_group(self, sidebar, "ОБЗОР", (("dashboard", "Дашборд"),)),
            "operations": _nav_group(
                self,
                sidebar,
                "ОПЕРАЦИИ",
                (("queue", "План отправки"), ("active", "Активные"), ("asteroids", "Астероиды")),
            ),
            "data": _nav_group(
                self,
                sidebar,
                "ДАННЫЕ",
                (("recon", "Разведка"), ("targets", "Цели"), ("history", "История")),
            ),
            "system": _nav_group(
                self,
                sidebar,
                "СИСТЕМА",
                (("settings", "Настройки"), ("logs", "Лог")),
            ),
        }

        bottom = tk.Frame(sidebar, bg=SURFACE_1, padx=SPACE_MD, pady=SPACE_LG)
        bottom.pack(side="bottom", fill="x")
        make_button(bottom, "Запустить браузер", self.launch_browser, "secondary", size="compact").pack(
            fill="x", pady=3
        )
        make_button(bottom, "Подключиться", self.connect_browser, "primary", size="compact").pack(
            fill="x", pady=3
        )
        tk.Label(bottom, text=f"v{self.settings.get('app_version', '')}" if False else "", bg=SURFACE_1).pack_forget()
        try:
            from config import APP_VERSION
            version_text = f"v{APP_VERSION}"
        except Exception:
            version_text = ""
        tk.Label(bottom, text=version_text, bg=SURFACE_1, fg=TEXT_3, font=FONT_CAPTION).pack(
            anchor="center", pady=(SPACE_SM, 0)
        )

        content = tk.Frame(self, bg=SURFACE_0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)

        topbar = tk.Frame(content, bg=SURFACE_0, padx=SPACE_XL, pady=SPACE_LG)
        topbar.grid(row=0, column=0, sticky="ew")
        tk.Label(
            topbar,
            textvariable=self.page_title_var,
            bg=SURFACE_0,
            fg=TEXT_1,
            font=FONT_PAGE_TITLE,
        ).pack(side="left")

        status = tk.Label(
            topbar,
            textvariable=self.status_var,
            bg=SURFACE_3,
            fg=TEXT_2,
            padx=SPACE_MD,
            pady=7,
            font=FONT_BODY_STRONG,
            highlightbackground=BORDER_1,
            highlightthickness=1,
        )
        status.pack(side="right")
        self.status_badge = status
        make_button(
            topbar,
            "Синхронизировать",
            self.sync_flights,
            "secondary",
            size="compact",
        ).pack(side="right", padx=SPACE_SM)

        self.page_host = tk.Frame(content, bg=SURFACE_0)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=SPACE_XL, pady=(0, SPACE_XL))
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
        _apply_semantic_tags(self)

    def show_page(self: Any, key: str) -> None:
        titles = {
            "dashboard": "Дашборд",
            "queue": "План отправки",
            "active": "Активные рейсы",
            "recon": "Разведка",
            "asteroids": "Астероиды",
            "debris": "Астероиды с обломками",
            "targets": "Цели",
            "history": "История",
            "settings": "Настройки",
            "logs": "Лог",
        }
        self.current_page = key
        self.page_title_var.set(titles.get(key, key))
        self.pages[key].tkraise()
        for nav_key, button in self.nav_buttons.items():
            selected = nav_key == key
            button.configure(
                bg=SURFACE_3 if selected else SURFACE_1,
                fg=TEXT_1 if selected else TEXT_2,
            )
            rail = getattr(button, "_nav_rail", None)
            if rail is not None:
                rail.configure(bg=ACCENT if selected else SURFACE_1)
        self.render_all()

    def build_dashboard(self: Any) -> None:
        page = self._new_page("dashboard")
        cards = tk.Frame(page, bg=SURFACE_0)
        cards.pack(fill="x")
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1)
        self._card(cards, "ЗАНЯТО СЛОТОВ", self.card_slots_var, "атаки / лимит").grid(
            row=0, column=0, sticky="ew", padx=(0, SPACE_SM)
        )
        self._card(cards, "В ОЧЕРЕДИ", self.card_queue_var, "готовы к отправке").grid(
            row=0, column=1, sticky="ew", padx=SPACE_SM
        )
        self._card(cards, "ЦЕЛЕЙ ПО МЕТАЛЛУ", self.card_targets_var, "есть актуальная разведка").grid(
            row=0, column=2, sticky="ew", padx=SPACE_SM
        )
        self._card(cards, "БЛИЖАЙШИЙ ВОЗВРАТ", self.card_return_var, "реальный таймер игры").grid(
            row=0, column=3, sticky="ew", padx=(SPACE_SM, 0)
        )

        actions = tk.Frame(page, bg=SURFACE_0, pady=SPACE_MD)
        actions.pack(fill="x")
        secondary = tk.Frame(actions, bg=SURFACE_0)
        secondary.pack(side="left")
        make_button(
            secondary, "Импортировать отчёты", self.import_from_browser, "secondary", size="compact"
        ).pack(side="left", padx=(0, 6))
        make_button(
            secondary, "Рассчитать времена", self.calculate_times, "secondary", size="compact"
        ).pack(side="left", padx=6)
        make_button(
            secondary, "Сформировать план", self.generate_queue, "primary", size="compact"
        ).pack(side="left", padx=6)

        self.auto_badge = tk.Label(
            actions,
            text="АВТО ВЫКЛ",
            bg=SURFACE_2,
            fg=TEXT_2,
            padx=10,
            pady=7,
            font=FONT_CAPTION,
        )
        self.auto_badge.pack(side="right")
        make_button(actions, "Отправить следующий", self.send_next, "warning").pack(
            side="right", padx=(SPACE_SM, SPACE_SM)
        )

        body = tk.Frame(page, bg=SURFACE_0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        recommended = self._section(
            body,
            "Рекомендованные цели",
            "больше металла — выше; только с данными разведки",
        )
        recommended.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tree_frame = tk.Frame(recommended, bg=SURFACE_2, padx=SPACE_SM, pady=SPACE_SM)
        tree_frame.pack(fill="both", expand=True)
        cols = ("rank", "player", "coord", "metal", "trip", "last")
        self.dashboard_tree, scroll = self._tree(
            tree_frame,
            cols,
            {
                "rank": "#",
                "player": "Игрок",
                "coord": "Координаты",
                "metal": "Металл",
                "trip": "Цикл",
                "last": "Последняя отправка",
            },
            {"rank": 45, "player": 120, "coord": 90, "metal": 100, "trip": 75, "last": 140},
        )
        self.dashboard_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.dashboard_tree.bind("<Double-1>", lambda _: self.send_selected_dashboard())

        active = self._section(body, "Активные атаки", "до прибытия и возврата")
        active.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        active_frame = tk.Frame(active, bg=SURFACE_2, padx=SPACE_SM, pady=SPACE_SM)
        active_frame.pack(fill="both", expand=True)
        cols2 = ("target", "arrival", "return")
        self.dashboard_active_tree, scroll2 = self._tree(
            active_frame,
            cols2,
            {"target": "Цель", "arrival": "До удара", "return": "До возврата"},
            {"target": 95, "arrival": 100, "return": 100},
        )
        self.dashboard_active_tree.pack(side="left", fill="both", expand=True)
        scroll2.pack(side="right", fill="y")

    def build_queue_page(self: Any) -> None:
        page = self._new_page("queue")
        groups = tk.Frame(page, bg=SURFACE_0)
        groups.pack(fill="x", pady=(0, SPACE_MD))
        groups.grid_columnconfigure(0, weight=1)
        groups.grid_columnconfigure(1, weight=2)

        plan_card, plan = _control_group(groups, "ПЛАН")
        plan_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM), pady=(0, SPACE_SM))
        size_block = _spin_field(self, plan, "Размер", self.queue_size_var, 1, 200, 5)
        size_block.pack(side="left", padx=(0, SPACE_MD))
        make_button(plan, "Сформировать", self.generate_queue, "primary", size="compact").pack(
            side="left", pady=(16, 0)
        )

        send_card, send = _control_group(groups, "ОТПРАВКА")
        send_card.grid(row=0, column=1, sticky="nsew", padx=(SPACE_SM, 0), pady=(0, SPACE_SM))
        make_button(send, "Подготовить", self.prepare_selected_queue, "secondary", size="compact").pack(
            side="left", padx=(0, 6)
        )
        make_button(send, "Отправить следующий", self.send_next, "warning", size="compact").pack(
            side="left", padx=6
        )
        make_button(send, "Отправить волну", self.send_wave, "warning", size="compact").pack(
            side="left", padx=6
        )

        manage_card, manage = _control_group(groups, "УПРАВЛЕНИЕ СПИСКОМ")
        manage_card.grid(row=1, column=0, columnspan=2, sticky="ew")
        make_button(
            manage,
            "Снять зависшие статусы",
            self.reset_stuck_sending,
            "secondary",
            size="compact",
        ).pack(side="left")
        make_button(manage, "Очистить", self.clear_queue, "secondary", size="compact").pack(
            side="right", padx=(6, 0)
        )
        make_button(manage, "Удалить", self.remove_queue_selected, "danger", size="compact").pack(
            side="right", padx=6
        )
        make_button(manage, "↓", lambda: self.move_queue(1), "ghost", size="compact").pack(
            side="right", padx=3
        )
        make_button(manage, "↑", lambda: self.move_queue(-1), "ghost", size="compact").pack(
            side="right", padx=3
        )

        panel = self._section(
            page,
            "План отправки",
            "поставьте галочки для волны; без галочек «следующий» идёт по металлу",
        )
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=SURFACE_2, padx=SPACE_SM, pady=SPACE_SM)
        frame.pack(fill="both", expand=True)
        cols = (
            "picked",
            "position",
            "coord",
            "player",
            "energy",
            "metal",
            "minerals",
            "resource_gas",
            "total",
            "spy_at",
            "trip",
            "score",
            "last",
            "state",
        )
        self.queue_tree, scroll = self._tree(
            frame,
            cols,
            {
                "picked": "✓",
                "position": "#",
                "coord": "Координаты",
                "player": "Игрок",
                "energy": "Энергия",
                "metal": "Металл",
                "minerals": "Минералы",
                "resource_gas": "Газ",
                "total": "Всего",
                "spy_at": "Разведка",
                "trip": "Полный цикл",
                "score": "Приоритет",
                "last": "Последняя отправка",
                "state": "Статус",
            },
            {
                "picked": 38,
                "position": 45,
                "coord": 95,
                "player": 140,
                "energy": 90,
                "trip": 100,
                "metal": 85,
                "minerals": 85,
                "resource_gas": 85,
                "total": 95,
                "spy_at": 145,
                "score": 95,
                "last": 150,
                "state": 90,
            },
            selectmode="extended",
        )
        self.queue_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.queue_tree.bind("<Button-1>", self._toggle_queue_checkbox)
        self.queue_tree.tag_configure("active", background=SUCCESS_BG)
        self.queue_tree.tag_configure("sending", background=INFO_BG)
        self.queue_tree.tag_configure("failed", background=ERROR_BG)
        self.queue_tree.tag_configure("sent", foreground=TEXT_3)

    def build_asteroids_page(self: Any) -> None:
        page = self._new_page("asteroids")
        controls = self._section(
            page,
            "Добыча с астероидов",
            "настройка волны, диапазона и безопасного окна",
        )
        controls.pack(fill="x", pady=(0, SPACE_MD))
        groups = tk.Frame(controls, bg=SURFACE_2, padx=SPACE_MD, pady=(0, SPACE_MD))
        groups.pack(fill="x")
        for column in range(3):
            groups.grid_columnconfigure(column, weight=1)

        fleet_card, fleet = _control_group(groups, "ФЛОТ")
        fleet_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM))
        _spin_field(self, fleet, "Рейсов", self.asteroid_max_flights_var, 1, 100).pack(
            side="left", padx=(0, SPACE_LG)
        )
        _spin_field(self, fleet, "Переработчиков", self.asteroid_recyclers_var, 1, 1000, 7).pack(
            side="left"
        )

        range_card, range_body = _control_group(groups, "ДИАПАЗОН")
        range_card.grid(row=0, column=1, sticky="nsew", padx=SPACE_SM)
        top = tk.Frame(range_body, bg=SURFACE_2)
        top.pack(fill="x")
        _spin_field(self, top, "Система от", self.asteroid_start_system_var, 1, 40).pack(
            side="left", padx=(0, SPACE_LG)
        )
        _spin_field(self, top, "До", self.asteroid_end_system_var, 1, 40).pack(side="left")
        home = tk.Frame(range_body, bg=SURFACE_2)
        home.pack(fill="x", pady=(SPACE_MD, 0))
        self.make_field_label(home, "Исходная планета").pack(anchor="w")
        home_inputs = tk.Frame(home, bg=SURFACE_2)
        home_inputs.pack(anchor="w", pady=(SPACE_SM, 0))
        for variable in (self.asteroid_home_g_var, self.asteroid_home_s_var, self.asteroid_home_p_var):
            self.make_spinbox(home_inputs, variable, from_=1, to=999, width=3).pack(
                side="left", padx=(0, 4), ipady=4
            )

        safety_card, safety = _control_group(groups, "БЕЗОПАСНОСТЬ")
        safety_card.grid(row=0, column=2, sticky="nsew", padx=(SPACE_SM, 0))
        _spin_field(self, safety, "Запас до движения, сек", self.asteroid_safety_var, 0, 300, 7).pack(
            side="left", padx=(0, SPACE_LG)
        )
        _spin_field(self, safety, "Пауза после возврата, мин", self.asteroid_buffer_var, 0, 120, 7).pack(
            side="left"
        )

        actions = tk.Frame(controls, bg=SURFACE_2, padx=SPACE_MD, pady=(0, SPACE_MD))
        actions.pack(fill="x")
        make_button(actions, "Сканировать", self.scan_asteroids_manual, "primary", size="compact").pack(
            side="left", padx=(0, 6)
        )
        make_button(
            actions, "Рассчитать волну", self.calculate_asteroid_wave, "secondary", size="compact"
        ).pack(side="left", padx=6)
        make_button(actions, "Отправить волну", self.send_asteroid_wave, "warning", size="compact").pack(
            side="left", padx=6
        )
        self.asteroid_auto_button = make_button(
            actions,
            "Запустить автопродление",
            self.toggle_asteroid_auto,
            "secondary",
            size="compact",
        )
        self.asteroid_auto_button.pack(side="left", padx=6)
        make_button(
            actions, "Остановить операцию", self.cancel_asteroid_operation, "danger", size="compact"
        ).pack(side="right", padx=(SPACE_SM, 0))
        self.asteroid_auto_badge = tk.Label(
            actions,
            text="АВТО ВЫКЛ",
            bg=SURFACE_3,
            fg=TEXT_2,
            padx=SPACE_MD,
            pady=6,
            font=FONT_CAPTION,
        )
        self.asteroid_auto_badge.pack(side="right")

        cards = tk.Frame(page, bg=SURFACE_0)
        cards.pack(fill="x", pady=(0, SPACE_MD))
        for column in range(5):
            cards.grid_columnconfigure(column, weight=1)
        self._card(cards, "СТАТУС", self.asteroid_status_var, "текущий этап").grid(
            row=0, column=0, sticky="ew", padx=(0, SPACE_SM)
        )
        self._card(cards, "КАНДИДАТОВ", self.asteroid_candidate_var, "обнаружено сканированием").grid(
            row=0, column=1, sticky="ew", padx=SPACE_SM
        )
        self._card(cards, "ГОТОВО", self.asteroid_ready_var, "рассчитано для отправки").grid(
            row=0, column=2, sticky="ew", padx=SPACE_SM
        )
        self._card(cards, "ОТПРАВЛЕНО", self.asteroid_sent_var, "в последнем цикле").grid(
            row=0, column=3, sticky="ew", padx=SPACE_SM
        )
        self._card(cards, "СЛЕДУЮЩИЙ ЦИКЛ", self.asteroid_next_var, "возврат последнего + запас").grid(
            row=0, column=4, sticky="ew", padx=(SPACE_SM, 0)
        )

        panel = self._section(
            page,
            "Астероиды и рассчитанные рейсы",
            "позиция автоматически переносится через 24: 3:38:24 → 3:39:1",
        )
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=SURFACE_2, padx=SPACE_SM, pady=SPACE_SM)
        frame.pack(fill="both", expand=True)
        cols = ("origin", "scanned", "next", "period", "one", "target", "shifts", "return", "status")
        self.asteroid_tree, scroll = self._tree(
            frame,
            cols,
            {
                "origin": "Найден",
                "scanned": "Время скана",
                "next": "След. движение",
                "period": "Период",
                "one": "Полёт туда",
                "target": "Цель при прилёте",
                "shifts": "Сдвигов",
                "return": "Полный цикл",
                "status": "Статус",
            },
            {
                "origin": 95,
                "scanned": 145,
                "next": 145,
                "period": 80,
                "one": 90,
                "target": 110,
                "shifts": 70,
                "return": 100,
                "status": 220,
            },
            selectmode="extended",
        )
        self.asteroid_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.asteroid_tree.tag_configure("ready", background=SUCCESS_BG)
        self.asteroid_tree.tag_configure("sent", foreground=SUCCESS)
        self.asteroid_tree.tag_configure("error", background=ERROR_BG)

    def build_settings_page(self: Any) -> None:
        page = self._new_page("settings")
        canvas = tk.Canvas(page, bg=SURFACE_0, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = tk.Frame(canvas, bg=SURFACE_0)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def sync_scrollregion(_: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", sync_scrollregion)
        canvas.bind("<Configure>", sync_width)

        tk.Label(
            content,
            text="Настройки сгруппированы по назначению; значения и сохранение не изменены.",
            bg=SURFACE_0,
            fg=TEXT_2,
            font=FONT_BODY,
            anchor="w",
        ).pack(fill="x", pady=(0, SPACE_MD))

        def group(title: str) -> tk.Frame:
            panel = self._section(content, title)
            panel.pack(fill="x", pady=(0, SPACE_MD))
            body = tk.Frame(panel, bg=SURFACE_2, padx=SPACE_LG, pady=(0, SPACE_MD))
            body.pack(fill="x")
            body.grid_columnconfigure(2, weight=1)
            return body

        def row(parent: tk.Frame, index: int, label: str, widget: tk.Widget, note: str = "") -> None:
            tk.Label(
                parent,
                text=label,
                bg=SURFACE_2,
                fg=TEXT_1,
                font=FONT_BODY_STRONG,
                anchor="w",
            ).grid(row=index, column=0, sticky="w", padx=(0, SPACE_LG), pady=SPACE_SM)
            widget.grid(row=index, column=1, sticky="w", pady=SPACE_SM)
            if note:
                tk.Label(
                    parent,
                    text=note,
                    bg=SURFACE_2,
                    fg=TEXT_3,
                    font=FONT_CAPTION,
                    anchor="w",
                    justify="left",
                    wraplength=420,
                ).grid(row=index, column=2, sticky="w", padx=(SPACE_LG, 0), pady=SPACE_SM)

        browser = group("БРАУЗЕР")
        row(
            browser,
            0,
            "CDP-порт",
            self.make_spinbox(browser, self.port_var, from_=1024, to=65535, width=8),
            "обычно 9222",
        )

        raids = group("РЕЙДЫ")
        home = tk.Frame(raids, bg=SURFACE_2)
        for variable in (self.home_g_var, self.home_s_var, self.home_p_var):
            self.make_spinbox(home, variable, from_=1, to=999, width=4).pack(side="left", padx=(0, 4))
        row(raids, 0, "Исходная планета", home, "Москва: 3 : 39 : 11")
        row(
            raids,
            1,
            "Мегатранспортировщиков",
            self.make_spinbox(raids, self.ship_count_var, from_=1, to=100000, width=8),
            "на один рейс",
        )
        row(
            raids,
            2,
            "Максимум слотов",
            self.make_spinbox(raids, self.max_slots_var, from_=1, to=100, width=8),
            "сейчас 15",
        )
        row(
            raids,
            3,
            "Мин. энергия",
            self.make_spinbox(raids, self.min_energy_var, from_=0, to=100000, width=8),
            "старый параметр; на план отправки не влияет",
        )
        row(
            raids,
            4,
            "Мин. металл для плана",
            self.make_spinbox(raids, self.min_metal_queue_var, from_=0, to=100000000, width=10),
            "по умолчанию 480 000; ниже цели не попадают в план",
        )
        row(
            raids,
            5,
            "Интервал повторного рейса",
            self.make_spinbox(raids, self.repeat_minutes_var, from_=1, to=1440, width=8),
            "сохраняется для истории; на порядок по металлу не влияет",
        )
        row(
            raids,
            6,
            "Автоинтервал",
            self.make_spinbox(raids, self.auto_interval_var, from_=10, to=3600, width=8),
            "секунд между попытками",
        )

        data = group("ДАННЫЕ")
        row(
            data,
            0,
            "Глубина докладов",
            self.make_spinbox(data, self.report_lookback_var, from_=1, to=720, width=8),
            "часов: старые страницы не импортируются",
        )

        automation = group("АВТОМАТИЗАЦИЯ И ПОДТВЕРЖДЕНИЯ")
        row(
            automation,
            0,
            "Автоматический режим",
            self.make_check(
                automation,
                self.auto_var,
                "Автоматически отправлять план",
                self.toggle_auto,
            ),
            "волна из свободных слотов; остановка при ошибке",
        )
        row(
            automation,
            1,
            "Одиночный рейс",
            self.make_check(automation, self.confirm_single_var, "Запрашивать подтверждение"),
        )
        row(
            automation,
            2,
            "Волна рейсов",
            self.make_check(automation, self.confirm_wave_var, "Запрашивать подтверждение"),
        )

        application = group("ПРИЛОЖЕНИЕ")
        row(
            application,
            0,
            "Уведомления",
            self.make_check(application, self.notify_var, "Сообщать о возврате"),
            "через трей / системный звук",
        )
        row(
            application,
            1,
            "Закрытие окна",
            self.make_check(application, self.tray_var, "Сворачивать в трей"),
        )

        actions = tk.Frame(content, bg=SURFACE_0, pady=(0, SPACE_XL))
        actions.pack(fill="x")
        make_button(actions, "Сохранить настройки", self.save_settings, "primary").pack(side="left")
        make_button(
            actions, "Создать резервную копию", self.manual_backup, "secondary", size="compact"
        ).pack(side="left", padx=SPACE_SM)
        make_button(
            actions, "Открыть папку данных", self.open_data_dir, "secondary", size="compact"
        ).pack(side="left", padx=SPACE_SM)
        make_button(actions, "Собрать EXE", self.show_build_info, "ghost", size="compact").pack(side="right")

    app_class._build_shell = build_shell
    app_class.show_page = show_page
    app_class._build_dashboard = build_dashboard
    app_class._build_queue_page = build_queue_page
    app_class._build_asteroids_page = build_asteroids_page
    app_class._build_settings_page = build_settings_page
    _INSTALLED_CLASSES.add(app_class)


def install_debris_layout(debris_module: Any) -> None:
    def build_debris_page(self: Any) -> None:
        page = self._new_page("debris")
        controls = self._section(
            page,
            "Астероиды с обломками",
            "полный скан галактик 1–3 и отправка по сохранённым наблюдениям",
        )
        controls.pack(fill="x", pady=(0, SPACE_MD))

        groups = tk.Frame(controls, bg=SURFACE_2, padx=SPACE_MD, pady=(0, SPACE_MD))
        groups.pack(fill="x")
        for column in range(3):
            groups.grid_columnconfigure(column, weight=1)

        fleet_card, fleet = _control_group(groups, "ФЛОТ")
        fleet_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_SM))
        _spin_field(self, fleet, "Переработчиков / рейс", self.debris_recyclers_var, 1, 1000, 7).pack(
            anchor="w"
        )

        safety_card, safety = _control_group(groups, "БЕЗОПАСНОСТЬ")
        safety_card.grid(row=0, column=1, sticky="nsew", padx=SPACE_SM)
        _spin_field(self, safety, "Запас до движения, сек", self.asteroid_safety_var, 0, 300, 7).pack(
            anchor="w"
        )

        scan_card, scan = _control_group(groups, "СКАН")
        scan_card.grid(row=0, column=2, sticky="nsew", padx=(SPACE_SM, 0))
        tk.Label(
            scan,
            text="1–3 × 40 систем",
            bg=SURFACE_2,
            fg=TEXT_1,
            font=FONT_BODY_STRONG,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            scan,
            text="полный проход 40 → 1 в каждой галактике",
            bg=SURFACE_2,
            fg=TEXT_3,
            font=FONT_CAPTION,
            anchor="w",
        ).pack(anchor="w", pady=(SPACE_SM, 0))

        actions = tk.Frame(controls, bg=SURFACE_2, padx=SPACE_MD, pady=(0, SPACE_MD))
        actions.pack(fill="x")
        make_button(
            actions,
            "Сканировать все галактики",
            self.scan_debris_asteroids,
            "primary",
            size="compact",
        ).pack(side="left", padx=(0, 6))
        make_button(
            actions,
            "Отправить выбранные",
            self.send_selected_debris_asteroids,
            "warning",
            size="compact",
        ).pack(side="left", padx=6)
        make_button(
            actions,
            "Остановить",
            self.cancel_debris_operation,
            "danger",
            size="compact",
        ).pack(side="right", padx=(SPACE_SM, 0))
        tk.Label(
            actions,
            textvariable=self.debris_status_var,
            bg=SURFACE_2,
            fg=TEXT_2,
            font=FONT_BODY_STRONG,
        ).pack(side="right", padx=(SPACE_MD, 0))

        stats = tk.Frame(page, bg=SURFACE_0)
        stats.pack(fill="x", pady=(0, SPACE_MD))
        for column in range(3):
            stats.grid_columnconfigure(column, weight=1)
        self._card(stats, "ПРОВЕРЕНО СИСТЕМ", self.debris_scanned_var, "из 120").grid(
            row=0, column=0, sticky="ew", padx=(0, SPACE_SM)
        )
        self._card(stats, "НАЙДЕНО С ОБЛОМКАМИ", self.debris_found_var, "последний полный скан").grid(
            row=0, column=1, sticky="ew", padx=SPACE_SM
        )
        self._card(stats, "ОТПРАВЛЕНО", self.debris_sent_var, "последняя операция").grid(
            row=0, column=2, sticky="ew", padx=(SPACE_SM, 0)
        )

        panel = self._section(
            page,
            "Найденные астероиды с обломками",
            "выдели одну или несколько строк; расчёт координат выполняется перед отправкой",
        )
        panel.pack(fill="both", expand=True)
        frame = tk.Frame(panel, bg=SURFACE_2, padx=SPACE_SM, pady=SPACE_SM)
        frame.pack(fill="both", expand=True)
        columns = ("coord", "scanned", "next", "period", "target", "one", "return", "status")
        self.debris_tree, scroll = self._tree(
            frame,
            columns,
            {
                "coord": "Найден",
                "scanned": "Время скана",
                "next": "След. движение",
                "period": "Период",
                "target": "Цель при отправке",
                "one": "Полёт туда",
                "return": "Полный цикл",
                "status": "Статус",
            },
            {
                "coord": 95,
                "scanned": 145,
                "next": 145,
                "period": 90,
                "target": 110,
                "one": 95,
                "return": 105,
                "status": 260,
            },
            selectmode="extended",
        )
        self.debris_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.debris_tree.tag_configure("sent", background=SUCCESS_BG)
        self.debris_tree.tag_configure("error", background=ERROR_BG)

    def add_debris_navigation(self: Any) -> None:
        operations = getattr(self, "_nav_group_frames", {}).get("operations")
        if operations is None:
            return
        _nav_item(self, operations, "debris", "Обломки")

    debris_module._build_debris_page = build_debris_page
    debris_module._add_debris_navigation = add_debris_navigation
