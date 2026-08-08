from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from v2.application.context import V2ApplicationContext
from v2.runtime_paths import RuntimePaths


class DiagnosticsPage(QWidget):
    """Show factual runtime/data-source information without probing the game."""

    def __init__(self, context: V2ApplicationContext, runtime_paths: RuntimePaths, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.runtime_paths = runtime_paths
        status = context.status()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        source = QFrame(self)
        source.setObjectName("InfoCard")
        source_layout = QGridLayout(source)
        source_layout.setContentsMargins(18, 16, 18, 16)
        source_layout.setHorizontalSpacing(20)
        source_layout.setVerticalSpacing(10)
        title = QLabel("Источники данных", source)
        title.setObjectName("SectionTitle")
        source_layout.addWidget(title, 0, 0, 1, 2)
        rows = (
            ("Legacy SQLite доступна", "Да" if status.available else "Нет"),
            ("Legacy SQLite режим", status.mode),
            ("Legacy SQLite", str(status.path)),
            ("Legacy SQLite проверка", status.detail),
        )
        for row, (label, value) in enumerate(rows, start=1):
            key = QLabel(label, source); key.setObjectName("Muted")
            val = QLabel(value, source); val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); val.setWordWrap(True)
            source_layout.addWidget(key, row, 0); source_layout.addWidget(val, row, 1)

        live_key = QLabel("Live-полёты", source); live_key.setObjectName("Muted")
        self.live_status_value = QLabel("Не проверены", source)
        self.live_status_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_layout.addWidget(live_key, 5, 0); source_layout.addWidget(self.live_status_value, 5, 1)
        live_detail_key = QLabel("Live источник", source); live_detail_key.setObjectName("Muted")
        self.live_detail_value = QLabel("Открой экран «Активные» для read-only проверки CDP.", source)
        self.live_detail_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.live_detail_value.setWordWrap(True)
        source_layout.addWidget(live_detail_key, 6, 0); source_layout.addWidget(self.live_detail_value, 6, 1)
        source_layout.setColumnStretch(1, 1)
        layout.addWidget(source)

        isolation = QFrame(self)
        isolation.setObjectName("InfoCard")
        isolation_layout = QGridLayout(isolation)
        isolation_layout.setContentsMargins(18, 16, 18, 16)
        isolation_layout.setHorizontalSpacing(20)
        isolation_layout.setVerticalSpacing(10)
        isolation_title = QLabel("Изолированное хранилище V2", isolation)
        isolation_title.setObjectName("SectionTitle")
        isolation_layout.addWidget(isolation_title, 0, 0, 1, 2)
        v2_rows = (
            ("Корень", runtime_paths.root),
            ("V2 SQLite", runtime_paths.database),
            ("V2 SQLite существует", "Да" if runtime_paths.database.is_file() else "Нет"),
            ("V2 settings", "Доступны" if context.v2_settings_available() else "Недоступны"),
            ("Browser profile", runtime_paths.browser_profile),
            ("Логи", runtime_paths.logs),
            ("Скриншоты", runtime_paths.screenshots),
            ("Бэкапы", runtime_paths.backups),
        )
        for row, (label, value) in enumerate(v2_rows, start=1):
            key = QLabel(label, isolation); key.setObjectName("Muted")
            val = QLabel(str(value), isolation); val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); val.setWordWrap(True)
            isolation_layout.addWidget(key, row, 0); isolation_layout.addWidget(val, row, 1)
        isolation_layout.setColumnStretch(1, 1)
        layout.addWidget(isolation)

        runtime = QFrame(self)
        runtime.setObjectName("InfoCard")
        runtime_layout = QGridLayout(runtime)
        runtime_layout.setContentsMargins(18, 16, 18, 16)
        runtime_layout.setHorizontalSpacing(20); runtime_layout.setVerticalSpacing(10)
        runtime_title = QLabel("Runtime", runtime); runtime_title.setObjectName("SectionTitle")
        runtime_layout.addWidget(runtime_title, 0, 0, 1, 2)
        runtime_rows = (
            ("Python", sys.version.split()[0]),
            ("PySide6", pyside_version),
            ("ОС", platform.platform()),
            ("UI режим", "V2 isolated writes + legacy/browser read-only"),
        )
        for row, (label, value) in enumerate(runtime_rows, start=1):
            key = QLabel(label, runtime); key.setObjectName("Muted")
            runtime_layout.addWidget(key, row, 0); runtime_layout.addWidget(QLabel(str(value), runtime), row, 1)
        runtime_layout.setColumnStretch(1, 1)
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
