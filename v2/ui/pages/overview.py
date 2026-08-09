from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.components import MetricCard, SectionCard, StateBanner, command_button, page_layout
from v2.ui.theme import SPACING


def _number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class OverviewPage(QWidget):
    """Dashboard from persisted facts plus the last explicit read-only live refresh."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        status = context.status()
        snapshot = context.overview()

        layout = page_layout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.storage_banner = StateBanner(
            "Рабочие данные подключены только для чтения"
            if status.available else "Рабочая база данных не подключена",
            "V2 показывает сохранённые факты из SQLite. Live-источник проверяется только после явного «Обновить live»."
            if status.available else f"Источник: {status.path}\n{status.detail}",
            tone="success" if status.available else "warning",
            parent=self,
        )
        layout.addWidget(self.storage_banner)

        value = (lambda n: _number(n)) if status.available else (lambda _n: "—")
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(SPACING["md"])
        metrics.setVerticalSpacing(SPACING["md"])
        metrics.addWidget(MetricCard("ВСЕГО ЦЕЛЕЙ", value(snapshot.targets_total), "Строк в targets", tone="info"), 0, 0)
        metrics.addWidget(MetricCard("АКТИВНЫЕ ЦЕЛИ", value(snapshot.targets_enabled), "Enabled и не в blacklist", tone="success"), 0, 1)
        metrics.addWidget(MetricCard("В ОЧЕРЕДИ", value(snapshot.queue_queued), "Состояние queued", tone="warning"), 0, 2)
        metrics.addWidget(MetricCard("ИСТОРИЯ", value(snapshot.history_total), "Записей отправок"), 0, 3)
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        live = SectionCard(
            "Live readiness",
            "Attach-only снимок флотов и ёмкости. Никакой live-проверки при открытии приложения.",
            object_name="CommandCard",
            parent=self,
        )
        live_header = QHBoxLayout()
        self.live_status = QLabel("Live-данные ещё не проверены", live)
        self.live_status.setObjectName("Muted")
        self.live_status.setWordWrap(True)
        live_header.addWidget(self.live_status, 1)
        self.live_refresh_button = command_button("Обновить live", tone="secondary", compact=True, parent=live)
        self.live_refresh_button.setObjectName("SecondaryButton")
        self.live_refresh_button.clicked.connect(self.refresh_live)
        live_header.addWidget(self.live_refresh_button)
        live.content_layout.addLayout(live_header)

        live_grid = QGridLayout()
        live_grid.setHorizontalSpacing(SPACING["xl"])
        live_grid.setVerticalSpacing(SPACING["sm"])
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
            row = (index // 4) * 2
            column = index % 4
            key = QLabel(label.upper(), live)
            key.setObjectName("MetricLabel")
            val = QLabel("—", live)
            val.setObjectName("BodyStrong")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            setattr(self, attr, val)
            live_grid.addWidget(key, row, column)
            live_grid.addWidget(val, row + 1, column)
            live_grid.setColumnStretch(column, 1)
        live.content_layout.addLayout(live_grid)
        layout.addWidget(live)
        self.render_live()

        freshness = SectionCard(
            "Последние сохранённые события",
            "Persisted evidence; время не подменяется текущим временем приложения.",
            parent=self,
        )
        freshness_grid = QGridLayout()
        freshness_grid.setHorizontalSpacing(SPACING["xl"])
        spy_label = QLabel("ПОСЛЕДНЯЯ РАЗВЕДКА", freshness)
        spy_label.setObjectName("MetricLabel")
        raid_label = QLabel("ПОСЛЕДНИЙ РЕЙД", freshness)
        raid_label.setObjectName("MetricLabel")
        spy_value = QLabel(snapshot.latest_spy_at or "—", freshness)
        spy_value.setObjectName("Mono")
        raid_value = QLabel(snapshot.latest_raid_at or "—", freshness)
        raid_value.setObjectName("Mono")
        freshness_grid.addWidget(spy_label, 0, 0)
        freshness_grid.addWidget(raid_label, 0, 1)
        freshness_grid.addWidget(spy_value, 1, 0)
        freshness_grid.addWidget(raid_value, 1, 1)
        freshness_grid.setColumnStretch(0, 1)
        freshness_grid.setColumnStretch(1, 1)
        freshness.content_layout.addLayout(freshness_grid)
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
