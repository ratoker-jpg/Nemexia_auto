from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.components import SectionCard, StateBanner, command_button, page_layout
from v2.ui.pages.read_tables import FilterableReadOnlyTable
from v2.ui.theme import SPACING


class ActivePage(QWidget):
    """Show typed live-flight facts and reconcile local V2 action uncertainty."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.capacity = None

        layout = page_layout(self)

        self.status_banner = StateBanner(
            "Live-полёты не проверены",
            "Открой fleets.php в браузере с CDP и нажми «Обновить». Чтение остаётся attach-only.",
            tone="info",
            parent=self,
        )
        self.status_title = self.status_banner.title
        self.status_detail = self.status_banner.detail
        layout.addWidget(self.status_banner)

        summary = SectionCard(
            "Live control",
            "Фактическая ёмкость флота и unresolved V2 journal показываются отдельно от строк полётов.",
            object_name="CommandCard",
            parent=self,
        )
        summary_row = QHBoxLayout()
        summary_row.setSpacing(SPACING["md"])
        self.capacity_label = QLabel("Лимит флота: —", summary)
        self.capacity_label.setObjectName("BodyStrong")
        self.capacity_label.setToolTip("Лимит не вычисляется по строкам таблицы")
        summary_row.addWidget(self.capacity_label, 1)
        self.refresh_button = command_button("Обновить", tone="secondary", compact=True, parent=summary)
        self.refresh_button.clicked.connect(self.reload_view)
        summary_row.addWidget(self.refresh_button)
        summary.content_layout.addLayout(summary_row)

        self.journal_label = QLabel("Журнал V2: —", summary)
        self.journal_label.setObjectName("Muted")
        self.journal_label.setWordWrap(True)
        summary.content_layout.addWidget(self.journal_label)
        layout.addWidget(summary)

        self.flight_table = FilterableReadOnlyTable(
            (
                "Откуда", "Куда", "Миссия", "Направление", "Scope",
                "В расчётах", "Таймер фарма", "Возврат", "Fleet ID",
            ),
            (),
            placeholder="Поиск по активным полётам…",
            parent=self,
        )
        self.flight_table.layout().setContentsMargins(0, 0, 0, 0)
        self.model = self.flight_table.model
        layout.addWidget(self.flight_table, 1)

    def reload_view(self) -> None:
        """Read live flights; only local V2 journal/queue may be reconciled."""
        self.refresh_button.setEnabled(False)
        self.status_title.setText("Проверяем live-полёты…")
        self.status_detail.setText("Читаю текущий DOM fleets.php через attach-only CDP.")
        reconciled = []
        try:
            status = self.context.refresh_live_source()
            flights = self.context.classified_active_flights() if status.available else []
            capacity = self.context.fleet_capacity() if status.available else None
            if status.available:
                reconciled = self.context.reconcile_raid_actions()
        except Exception as exc:
            status = None
            flights = []
            capacity = None
            self.status_title.setText("Live-полёты пока не подключены")
            self.status_detail.setText(f"Live-read остановлен: {exc}")
        else:
            self.status_title.setText(
                "Live-полёты подключены" if status.available else "Live-полёты пока не подключены"
            )
            detail = status.detail
            if reconciled:
                detail += f" · журнал: подтверждено {len(reconciled)}"
            self.status_detail.setText(detail)

        rows = [
            (
                item.raw.source,
                item.raw.target,
                item.raw.mission,
                item.facts.direction.value,
                item.facts.owner_scope.value,
                "Исключён" if item.facts.excluded else "Учитывается",
                "Блокирует" if item.facts.blocks_farm_cycle else "Нет",
                item.raw.return_at,
                item.raw.fleet_id,
            )
            for item in flights
        ]
        self.model.replace_rows(rows)
        self.capacity = capacity
        if capacity is None:
            self.capacity_label.setText("Лимит флота: —")
            self.capacity_label.setToolTip("Лимит не вычисляется по строкам таблицы")
        else:
            self.capacity_label.setText(
                f"Полёты: {capacity.used} / {capacity.maximum} · свободно {capacity.free}"
            )
            self.capacity_label.setToolTip(capacity.source)

        actions = self.context.recent_raid_actions(limit=200)
        unresolved = [item for item in actions if item.status in {"pending", "ambiguous"}]
        if not actions:
            self.journal_label.setText("Журнал V2: отправок пока нет")
        else:
            latest = actions[0]
            self.journal_label.setText(
                f"Журнал V2: {len(actions)} записей · unresolved {len(unresolved)} · "
                f"последняя {latest.request_id} → {latest.target} · {latest.status} · "
                f"fleet {latest.fleet_id or '—'}"
            )
        self.refresh_button.setEnabled(True)
