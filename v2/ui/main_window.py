from __future__ import annotations

import sys
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from v2.application.context import V2ApplicationContext
from v2.runtime_paths import RuntimePaths
from v2.ui.pages.active import ActivePage
from v2.ui.pages.asteroids import AsteroidsPage
from v2.ui.pages.diagnostics import DiagnosticsPage
from v2.ui.pages.farm import FarmPage
from v2.ui.pages.overview import OverviewPage
from v2.ui.pages.plan import PlanPage
from v2.ui.pages.read_tables import HistoryPage, TargetsPage
from v2.ui.pages.recon import ReconPage
from v2.ui.pages.settings import SettingsPage
from v2.ui.theme import ORBITAL_COMMAND_QSS


NAV_GROUPS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("ОБЗОР", (("overview", "Обзор", "Сводка состояния и ближайшие действия"),)),
    ("ОПЕРАЦИИ", (
        ("plan", "План", "Очередь и подготовка отправок"),
        ("active", "Активные", "Текущие полёты и возвраты"),
        ("farm", "Автофарм", "Состояние автоматического цикла"),
        ("asteroids", "Астероиды", "Разведка и добыча газа"),
        ("debris", "Обломки", "Астероиды с обломками"),
    )),
    ("ДАННЫЕ", (
        ("recon", "Разведка", "Шпионские отчёты и свежесть данных"),
        ("targets", "Цели", "База целей и фильтры"),
        ("history", "История", "Отправки, результаты и ошибки"),
    )),
    ("СИСТЕМА", (
        ("settings", "Настройки", "Параметры приложения"),
        ("diagnostics", "Диагностика", "Логи и техническое состояние"),
    )),
)


def _iter_pages() -> Iterable[tuple[str, str, str]]:
    for _group, pages in NAV_GROUPS:
        yield from pages


class MainWindow(QMainWindow):
    """Side-by-side V2 shell with explicit service boundaries."""

    def __init__(self, runtime_paths: RuntimePaths, context: V2ApplicationContext) -> None:
        super().__init__()
        self.runtime_paths = runtime_paths
        self.context = context
        self.setWindowTitle("Nemexia Raid Manager V2")
        self.setMinimumSize(1180, 720)
        self.resize(1440, 900)

        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        content = QWidget(root)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root_layout.addWidget(content, 1)

        self.topbar = self._build_topbar()
        content_layout.addWidget(self.topbar)

        self.stack = QStackedWidget(content)
        self.stack.setContentsMargins(24, 24, 24, 24)
        content_layout.addWidget(self.stack, 1)

        self._page_index: dict[str, int] = {}
        for key, title, description in _iter_pages():
            index = self.stack.addWidget(self._build_page(key, title, description))
            self._page_index[key] = index

        first = self._nav_buttons["overview"]
        first.setChecked(True)
        self._show_page("overview", "Обзор", "Сводка состояния и ближайшие действия")

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(4)

        brand = QLabel("NEMEXIA", sidebar)
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        accent = QLabel("ORBITAL COMMAND · V2", sidebar)
        accent.setObjectName("BrandAccent")
        layout.addWidget(accent)
        layout.addSpacing(18)

        self._button_group = QButtonGroup(sidebar)
        self._button_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}

        for group_name, pages in NAV_GROUPS:
            group_label = QLabel(group_name, sidebar)
            group_label.setObjectName("SectionLabel")
            layout.addSpacing(8)
            layout.addWidget(group_label)
            for key, title, description in pages:
                button = QPushButton(title, sidebar)
                button.setObjectName("NavButton")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda _checked=False, k=key, t=title, d=description: self._show_page(k, t, d)
                )
                self._button_group.addButton(button)
                self._nav_buttons[key] = button
                layout.addWidget(button)

        layout.addStretch(1)
        version = QLabel("V2 preview · legacy runtime untouched", sidebar)
        version.setObjectName("Muted")
        version.setWordWrap(True)
        layout.addWidget(version)
        return sidebar

    def _build_topbar(self) -> QFrame:
        topbar = QFrame(self)
        topbar.setObjectName("Topbar")
        topbar.setFixedHeight(76)
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(24, 10, 24, 10)

        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        self.page_title = QLabel("Обзор", topbar)
        self.page_title.setObjectName("PageTitle")
        self.page_description = QLabel("", topbar)
        self.page_description.setObjectName("PageDescription")
        title_block.addWidget(self.page_title)
        title_block.addWidget(self.page_description)
        layout.addLayout(title_block, 1)

        data_status = self.context.status()
        text = "Рабочая БД · только чтение" if data_status.available else "Данные недоступны · preview"
        status = QLabel(text, topbar)
        status.setObjectName("StatusBadge")
        status.setToolTip(f"{data_status.path}\n{data_status.detail}")
        status.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(status)
        return topbar

    def _build_page(self, key: str, title: str, description: str) -> QWidget:
        if key == "overview":
            return OverviewPage(self.context, self)
        if key == "plan":
            return PlanPage(self.context, self)
        if key == "active":
            return ActivePage(self.context, self)
        if key == "farm":
            return FarmPage(self.context, self)
        if key == "asteroids":
            return AsteroidsPage(self.context, self)
        if key == "recon":
            return ReconPage(self.context, self)
        if key == "targets":
            return TargetsPage(self.context, self)
        if key == "history":
            return HistoryPage(self.context, self)
        if key == "settings":
            return SettingsPage(self.context, self)
        if key == "diagnostics":
            return DiagnosticsPage(self.context, self.runtime_paths, self)
        return self._placeholder_page(title, description)

    def _placeholder_page(self, title: str, description: str) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        card = QFrame(page)
        card.setObjectName("PlaceholderCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(6)
        title_label = QLabel(title, card)
        title_label.setObjectName("PlaceholderTitle")
        description_label = QLabel(description, card)
        description_label.setObjectName("Muted")
        description_label.setWordWrap(True)
        note = QLabel("Экран подключится к V2 services поэтапно. Игровые действия здесь пока отключены.", card)
        note.setObjectName("Muted")
        note.setWordWrap(True)
        card_layout.addWidget(title_label)
        card_layout.addWidget(description_label)
        card_layout.addSpacing(8)
        card_layout.addWidget(note)
        layout.addWidget(card)
        return page

    def _show_page(self, key: str, title: str, description: str) -> None:
        index = self._page_index.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.page_title.setText(title)
        self.page_description.setText(description)
        button = self._nav_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        page = self.stack.widget(index)
        reloader = getattr(page, "reload_view", None)
        if callable(reloader):
            reloader()


def run_qt_app(runtime_paths: RuntimePaths, context: V2ApplicationContext) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Nemexia Raid Manager V2")
    app.setStyleSheet(ORBITAL_COMMAND_QSS)
    window = MainWindow(runtime_paths, context)
    window.show()
    return app.exec()
