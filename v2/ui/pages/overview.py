from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

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
    """Dashboard made only from facts already persisted in SQLite."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
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
