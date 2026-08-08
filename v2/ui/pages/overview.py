from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from v2.application.context import V2ApplicationContext


def _number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class MetricCard(QFrame):
    def __init__(self, label: str, value: str, hint: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        title = QLabel(label, self)
        title.setObjectName("MetricLabel")
        number = QLabel(value, self)
        number.setObjectName("MetricValue")
        detail = QLabel(hint, self)
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(number)
        layout.addWidget(detail)


class OverviewPage(QWidget):
    """Dashboard from persisted facts plus the last explicit read-only live refresh."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        status = context.status()
        snapshot = context.overview()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        banner = QFrame(self)
        banner.setObjectName("InfoCard")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(18, 14, 18, 14)
        banner_title = QLabel(
            "Рабочие данные подключены только для чтения"
            if status.available
            else "Рабочая база данных не подключена",
            banner,
        )
        banner_title.setObjectName("SectionTitle")
        banner_text = QLabel(
            "V2 показывает сохранённые факты из SQLite и пока не выполняет игровые действия."
            if status.available
            else f"Источник: {status.path}\n{status.detail}",
            banner,
        )
        banner_text.setObjectName("Muted")
        banner_text.setWordWrap(True)
        banner_layout.addWidget(banner_title)
        banner_layout.addWidget(banner_text)
        layout.addWidget(banner)

        value = (lambda n: _number(n)) if status.available else (lambda _n: "—")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.addWidget(MetricCard("Всего целей", value(snapshot.targets_total), "Строк в targets"), 0, 0)
        grid.addWidget(MetricCard("Активные цели", value(snapshot.targets_enabled), "Enabled и не в blacklist"), 0, 1)
        grid.addWidget(MetricCard("В очереди", value(snapshot.queue_queued), "Состояние queued"), 0, 2)
        grid.addWidget(MetricCard("История", value(snapshot.history_total), "Записей отправок"), 0, 3)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        live = QFrame(self)
        live.setObjectName("InfoCard")
        live_layout = QGridLayout(live)
        live_layout.setContentsMargins(18, 16, 18, 16)
        live_layout.setHorizontalSpacing(24)
        live_layout.setVerticalSpacing(8)
        heading = QHBoxLayout()
        live_title = QLabel("Live-состояние", live)
        live_title.setObjectName("SectionTitle")
        heading.addWidget(live_title, 1)
        self.live_refresh_button = QPushButton("Обновить live", live)
        self.live_refresh_button.setObjectName("SecondaryButton")
        self.live_refresh_button.clicked.connect(self.refresh_live)
        heading.addWidget(self.live_refresh_button)
        live_layout.addLayout(heading, 0, 0, 1, 4)

        self.live_status = QLabel("Live-данные ещё не проверены", live)
        self.live_status.setObjectName("Muted")
        self.live_status.setWordWrap(True)
        live_layout.addWidget(self.live_status, 1, 0, 1, 4)

        labels = (
            ("Слоты", "live_capacity"),
            ("Активные", "live_active"),
            ("Свои исходящие", "live_personal"),
            ("Таймер фарма", "live_farm"),
            ("Исключено", "live_excluded"),
            ("Последний возврат", "live_return"),
            ("Буфер", "live_buffer"),
            ("Можно снова", "live_ready"),
        )
        for index, (label, attr) in enumerate(labels):
            row = 2 + index // 4 * 2
            column = index % 4
            key = QLabel(label, live)
            key.setObjectName("Muted")
            val = QLabel("—", live)
            setattr(self, attr, val)
            live_layout.addWidget(key, row, column)
            live_layout.addWidget(val, row + 1, column)
            live_layout.setColumnStretch(column, 1)
        layout.addWidget(live)
        self.render_live()

        freshness = QFrame(self)
        freshness.setObjectName("InfoCard")
        freshness_layout = QGridLayout(freshness)
        freshness_layout.setContentsMargins(18, 16, 18, 16)
        freshness_layout.setHorizontalSpacing(24)
        title = QLabel("Последние сохранённые события", freshness)
        title.setObjectName("SectionTitle")
        freshness_layout.addWidget(title, 0, 0, 1, 2)
        spy_label = QLabel("Последняя разведка", freshness)
        spy_label.setObjectName("Muted")
        raid_label = QLabel("Последний рейд", freshness)
        raid_label.setObjectName("Muted")
        freshness_layout.addWidget(spy_label, 1, 0)
        freshness_layout.addWidget(raid_label, 1, 1)
        freshness_layout.addWidget(QLabel(snapshot.latest_spy_at or "—", freshness), 2, 0)
        freshness_layout.addWidget(QLabel(snapshot.latest_raid_at or "—", freshness), 2, 1)
        layout.addWidget(freshness)
        layout.addStretch(1)

    def refresh_live(self) -> None:
        """User-triggered attach-only refresh; Overview never probes at construction."""
        self.live_refresh_button.setEnabled(False)
        self.live_status.setText("Проверяем live-состояние…")
        try:
            self.context.refresh_live_source()
        finally:
            self.render_live()
            self.live_refresh_button.setEnabled(True)

    def render_live(self) -> None:
        snapshot = self.context.live_overview_snapshot()
        self.live_status.setText(snapshot.detail)
        if not snapshot.available:
            for attr in (
                "live_capacity", "live_active", "live_personal", "live_farm",
                "live_excluded", "live_return", "live_ready",
            ):
                getattr(self, attr).setText("—")
            self.live_buffer.setText(f"{snapshot.return_buffer_minutes} мин")
            return

        capacity = snapshot.capacity
        self.live_capacity.setText(
            f"{capacity.used} / {capacity.maximum} · свободно {capacity.free}"
            if capacity is not None else "—"
        )
        self.live_active.setText(str(snapshot.active_count))
        self.live_personal.setText(str(snapshot.personal_outgoing_count))
        self.live_farm.setText(str(snapshot.farm_blocking_count))
        self.live_excluded.setText(str(snapshot.excluded_count))
        self.live_return.setText(snapshot.latest_farm_return_at or "—")
        self.live_buffer.setText(f"{snapshot.return_buffer_minutes} мин")
        self.live_ready.setText(snapshot.effective_farm_ready_at or "—")
