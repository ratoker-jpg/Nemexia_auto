from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class ActivePage(QWidget):
    """Show live flights only when an explicit flight source is available."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        status = context.flight_status()
        flights = context.active_flights() if status.available else []
        capacity = context.fleet_capacity() if status.available else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        banner = QFrame(self)
        banner.setObjectName("InfoCard")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel(
            "Live-полёты подключены" if status.available else "Live-полёты пока не подключены",
            banner,
        )
        title.setObjectName("SectionTitle")
        detail = QLabel(status.detail, banner)
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        if capacity is None:
            capacity_text = "Лимит флота: —"
        else:
            capacity_text = (
                f"Полёты: {capacity.used} / {capacity.maximum} · свободно {capacity.free}"
            )
        capacity_label = QLabel(capacity_text, banner)
        capacity_label.setObjectName("Muted")
        capacity_label.setToolTip(
            capacity.source if capacity is not None else "Лимит не вычисляется по строкам таблицы"
        )
        banner_layout.addWidget(title)
        banner_layout.addWidget(detail)
        banner_layout.addWidget(capacity_label)
        layout.addWidget(banner)

        rows = [
            (
                item.source,
                item.target,
                item.mission,
                item.departure_at,
                item.arrival_at,
                item.return_at,
                item.fleet_id,
            )
            for item in flights
        ]
        self.flight_table = FilterableReadOnlyTable(
            ("Откуда", "Куда", "Миссия", "Отправление", "Прибытие", "Возврат", "Fleet ID"),
            rows,
            placeholder="Поиск по активным полётам…",
            parent=self,
        )
        self.model = self.flight_table.model
        self.capacity = capacity
        layout.addWidget(self.flight_table, 1)
