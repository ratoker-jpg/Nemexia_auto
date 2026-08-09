from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from v2.application.context import V2ApplicationContext
from v2.runtime_paths import RuntimePaths
from v2.ui.components import SectionCard, StateBanner, scrollable_page
from v2.ui.theme import SPACING


def _add_fact_rows(card: SectionCard, rows: tuple[tuple[str, object], ...], *, mono_values: bool = False) -> None:
    grid = QGridLayout()
    grid.setHorizontalSpacing(SPACING["xl"])
    grid.setVerticalSpacing(SPACING["sm"])
    for row, (label, value) in enumerate(rows):
        key = QLabel(label, card)
        key.setObjectName("MetricLabel")
        val = QLabel(str(value), card)
        if mono_values:
            val.setObjectName("Mono")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        val.setWordWrap(True)
        grid.addWidget(key, row, 0)
        grid.addWidget(val, row, 1)
    grid.setColumnStretch(1, 1)
    card.content_layout.addLayout(grid)


class DiagnosticsPage(QWidget):
    """Show factual runtime/data-source information without probing the game."""

    def __init__(self, context: V2ApplicationContext, runtime_paths: RuntimePaths, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.runtime_paths = runtime_paths
        status = context.status()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll, _content, layout = scrollable_page(self)
        outer.addWidget(scroll)

        boundary = StateBanner(
            "No-probe diagnostics",
            "Этот экран показывает только локальные/runtime факты и последний уже выполненный live-read. "
            "Чтобы проверить CDP, используй явное read-only обновление на экране «Активные».",
            tone="info",
            parent=self,
        )
        layout.addWidget(boundary)

        source = SectionCard(
            "Источники данных",
            "Legacy SQLite остаётся read-only; live browser status здесь не инициируется.",
            object_name="DefinitionCard",
            parent=self,
        )
        _add_fact_rows(
            source,
            (
                ("Legacy SQLite доступна", "Да" if status.available else "Нет"),
                ("Legacy SQLite режим", status.mode),
                ("Legacy SQLite", status.path),
                ("Legacy SQLite проверка", status.detail),
            ),
            mono_values=True,
        )
        live_grid = QGridLayout()
        live_grid.setHorizontalSpacing(SPACING["xl"])
        live_grid.setVerticalSpacing(SPACING["sm"])
        live_key = QLabel("Live-полёты", source)
        live_key.setObjectName("MetricLabel")
        self.live_status_value = QLabel("Не проверены", source)
        self.live_status_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        live_detail_key = QLabel("Live источник", source)
        live_detail_key.setObjectName("MetricLabel")
        self.live_detail_value = QLabel("Открой экран «Активные» для read-only проверки CDP.", source)
        self.live_detail_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.live_detail_value.setWordWrap(True)
        live_grid.addWidget(live_key, 0, 0)
        live_grid.addWidget(self.live_status_value, 0, 1)
        live_grid.addWidget(live_detail_key, 1, 0)
        live_grid.addWidget(self.live_detail_value, 1, 1)
        live_grid.setColumnStretch(1, 1)
        source.content_layout.addLayout(live_grid)
        layout.addWidget(source)

        isolation = SectionCard(
            "Изолированное хранилище V2",
            "Локальные пути показаны для диагностики и доступны для выделения; этот экран ничего не создаёт и не захватывает.",
            object_name="DefinitionCard",
            parent=self,
        )
        _add_fact_rows(
            isolation,
            (
                ("Корень", runtime_paths.root),
                ("V2 SQLite", runtime_paths.database),
                ("V2 SQLite существует", "Да" if runtime_paths.database.is_file() else "Нет"),
                ("V2 settings", "Доступны" if context.v2_settings_available() else "Недоступны"),
                ("Browser profile", runtime_paths.browser_profile),
                ("Логи", runtime_paths.logs),
                ("Скриншоты", runtime_paths.screenshots),
                ("Бэкапы", runtime_paths.backups),
            ),
            mono_values=True,
        )
        layout.addWidget(isolation)

        runtime = SectionCard(
            "Runtime",
            "Фактическое локальное окружение текущего opt-in Qt процесса.",
            object_name="DefinitionCard",
            parent=self,
        )
        _add_fact_rows(
            runtime,
            (
                ("Python", sys.version.split()[0]),
                ("PySide6", pyside_version),
                ("ОС", platform.platform()),
                ("UI режим", "V2 isolated writes + legacy/browser read-only"),
            ),
        )
        layout.addWidget(runtime)
        layout.addStretch(1)
        self.reload_view()

    def reload_view(self) -> None:
        """Reflect the last explicit live probe; never initiate one from Diagnostics."""
        flight_status = self.context.cached_flight_status()
        if flight_status is None:
            self.live_status_value.setText("Не проверены")
            self.live_detail_value.setText("Открой экран «Активные» для read-only проверки CDP.")
            return
        self.live_status_value.setText("Доступны" if flight_status.available else "Недоступны")
        self.live_detail_value.setText(flight_status.detail)
