from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from v2.application.context import V2ApplicationContext
from v2.application.read_store import QueueSnapshot
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class PlanPage(FilterableReadOnlyTable):
    """V2-owned raid queue with explicit, user-confirmed manual actions."""

    HEADERS = (
        "#", "Координаты", "Игрок", "Металл", "Минералы", "Газ",
        "Разведка", "Состояние очереди", "Цель",
    )

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        self.context = context
        self._items: tuple[QueueSnapshot, ...] = tuple(context.plan())
        super().__init__(
            self.HEADERS,
            self._rows(self._items),
            placeholder="Поиск по очереди V2…",
            parent=parent,
        )

        controls = QFrame(self)
        controls.setObjectName("InfoCard")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(10)

        controls_layout.addWidget(QLabel("Мегатранспортировщиков", controls))
        self.ship_count = QSpinBox(controls)
        self.ship_count.setRange(1, 100000)
        self.ship_count.setValue(25)
        controls_layout.addWidget(self.ship_count)

        self.prepare_button = QPushButton("Подготовить выбранную", controls)
        self.prepare_button.clicked.connect(self.prepare_selected)
        controls_layout.addWidget(self.prepare_button)

        self.send_button = QPushButton("Отправить выбранную", controls)
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.clicked.connect(self.send_selected)
        controls_layout.addWidget(self.send_button)

        self.action_status = QLabel("Выбери строку очереди.", controls)
        self.action_status.setObjectName("Muted")
        self.action_status.setWordWrap(True)
        controls_layout.addWidget(self.action_status, 1)
        self.layout().insertWidget(1, controls)
        self._update_action_gate()

    @staticmethod
    def _rows(items: tuple[QueueSnapshot, ...] | list[QueueSnapshot]):
        return [
            (
                item.position,
                item.coord,
                item.player,
                item.metal,
                item.minerals,
                item.gas,
                item.last_spy_at,
                item.state,
                "Blacklist" if item.blacklisted else ("Включена" if item.enabled else "Выключена"),
            )
            for item in items
        ]

    def reload_view(self) -> None:
        self._items = tuple(self.context.plan())
        self.model.replace_rows(self._rows(self._items))
        self._update_action_gate()

    def _update_action_gate(self) -> None:
        enabled = self.context.raid_actions_enabled()
        self.prepare_button.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if not enabled:
            self.action_status.setText("Действия V2 выключены в Настройках.")

    def _selected_item(self) -> QueueSnapshot | None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.information(self, "План", "Сначала выбери одну строку очереди.")
            return None
        source_index = self.proxy.mapToSource(selection[0])
        if not source_index.isValid() or source_index.row() >= len(self._items):
            QMessageBox.warning(self, "План", "Выбранная строка устарела. Обнови экран План.")
            return None
        return self._items[source_index.row()]

    def prepare_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if item.state != "queued":
            QMessageBox.warning(self, "Подготовка", f"Строка имеет состояние «{item.state}», а не queued.")
            return
        self._set_busy(True, f"Подготовка {item.coord}…")
        try:
            result = self.context.prepare_raid(item.coord, item.player, self.ship_count.value())
        except Exception as exc:
            self.action_status.setText(f"Подготовка остановлена: {exc}")
        else:
            gas = "—" if result.gas_needed is None else str(result.gas_needed)
            self.action_status.setText(
                f"Готово: {result.source} → {result.target} · {result.ship_count} шт. · "
                f"туда {result.one_way_seconds} с · газ {gas}. Флот ещё не отправлен."
            )
        finally:
            self._set_busy(False)

    def send_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if item.state != "queued":
            QMessageBox.warning(self, "Отправка", f"Строка имеет состояние «{item.state}», а не queued.")
            return
        count = self.ship_count.value()
        home = str(self.context.v2_setting("farm_home", "—"))
        answer = QMessageBox.question(
            self,
            "Подтверждение отправки",
            f"Отправить Атаку?\n\nОткуда: {home}\nЦель: {item.coord}\n"
            f"Игрок: {item.player}\nМегатранспортировщиков: {count}\n\n"
            "Будет выполнена одна попытка SendFleet. При неоднозначном ответе V2 НЕ повторит её автоматически.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        request_id = f"manual-{uuid.uuid4().hex}"
        self._set_busy(True, f"Отправка {item.coord} · {request_id[:15]}…")
        try:
            result = self.context.dispatch_plan_raid(
                queue_id=item.id,
                target=item.coord,
                player=item.player,
                ship_count=count,
                request_id=request_id,
            )
        except Exception as exc:
            self.action_status.setText(
                f"Отправка остановлена: {exc} · request {request_id}. "
                "Если статус неоднозначный — сначала проверь «Активные»."
            )
        else:
            if result.verified:
                self.action_status.setText(
                    f"Подтверждено: {item.coord} · fleet #{result.fleet_id or '—'} · request {request_id}."
                )
            else:
                self.action_status.setText(
                    f"Игра приняла запрос, но новый fleet не подтверждён · request {request_id}. "
                    "Повтор заблокирован до разбирательства."
                )
        finally:
            self.reload_view()
            self._set_busy(False)

    def _set_busy(self, busy: bool, text: str | None = None) -> None:
        if text:
            self.action_status.setText(text)
        enabled = (not busy) and self.context.raid_actions_enabled()
        self.prepare_button.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.ship_count.setEnabled(not busy)
