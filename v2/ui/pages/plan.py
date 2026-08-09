from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
)

from v2.application.context import V2ApplicationContext
from v2.application.read_store import QueueSnapshot
from v2.ui.components import SectionCard, StateBanner, command_button
from v2.ui.pages.read_tables import FilterableReadOnlyTable
from v2.ui.theme import SPACING


class PlanPage(FilterableReadOnlyTable):
    """V2-owned raid queue with deterministic local refill and explicit raid actions."""

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

        builder = SectionCard(
            "Сборка V2-очереди",
            "Локальная deterministic policy: browser не вызывается; protected sending/sent/ambiguous строки сохраняются.",
            object_name="CommandCard",
            parent=self,
        )
        builder_grid = QGridLayout()
        builder_grid.setHorizontalSpacing(SPACING["md"])
        builder_grid.setVerticalSpacing(SPACING["sm"])

        builder_grid.addWidget(QLabel("РЕЖИМ", builder), 0, 0)
        self.queue_mode = QComboBox(builder)
        self.queue_mode.addItem("Металл", "metal")
        self.queue_mode.addItem("Минералы", "minerals")
        self.queue_mode.addItem("AutoFarm ≥500k", "autofarm")
        self.queue_mode.setMaximumWidth(180)
        builder_grid.addWidget(self.queue_mode, 1, 0)

        builder_grid.addWidget(QLabel("ЦЕЛЕЙ", builder), 0, 1)
        self.queue_size = QSpinBox(builder)
        self.queue_size.setRange(1, 5000)
        self.queue_size.setValue(45)
        self.queue_size.setMaximumWidth(120)
        builder_grid.addWidget(self.queue_size, 1, 1)

        builder_grid.addWidget(QLabel("МИН. МЕТАЛЛ", builder), 0, 2)
        self.minimum_metal = QSpinBox(builder)
        self.minimum_metal.setRange(0, 2_000_000_000)
        self.minimum_metal.setSingleStep(10_000)
        self.minimum_metal.setValue(480_000)
        self.minimum_metal.setMaximumWidth(180)
        builder_grid.addWidget(self.minimum_metal, 1, 2)
        builder_grid.setColumnStretch(3, 1)

        builder_actions = QHBoxLayout()
        self.preview_refill_button = command_button("Предпросмотр", tone="secondary", compact=True, parent=builder)
        self.preview_refill_button.clicked.connect(self.preview_refill)
        builder_actions.addWidget(self.preview_refill_button)
        self.apply_refill_button = command_button("Пересобрать V2-очередь", tone="primary", compact=True, parent=builder)
        self.apply_refill_button.clicked.connect(self.apply_refill)
        builder_actions.addWidget(self.apply_refill_button)
        builder_actions.addStretch(1)
        builder_grid.addLayout(builder_actions, 2, 0, 1, 4)
        builder.content_layout.addLayout(builder_grid)

        self.refill_status = QLabel("Pure policy: browser не вызывается.", builder)
        self.refill_status.setObjectName("Muted")
        self.refill_status.setWordWrap(True)
        builder.content_layout.addWidget(self.refill_status)
        self.layout().insertWidget(1, builder)

        controls = SectionCard(
            "Контролируемая отправка",
            "Подготовка остаётся read-only. «Отправить выбранную» — подтверждаемая удалённая мутация с одной попыткой SendFleet.",
            object_name="CommandCard",
            parent=self,
        )
        controls_grid = QGridLayout()
        controls_grid.setHorizontalSpacing(SPACING["sm"])
        controls_grid.setVerticalSpacing(SPACING["sm"])
        ship_label = QLabel("МЕГАТРАНСПОРТИРОВЩИКИ", controls)
        ship_label.setObjectName("MetricLabel")
        controls_grid.addWidget(ship_label, 0, 0)
        self.ship_count = QSpinBox(controls)
        self.ship_count.setRange(1, 100000)
        self.ship_count.setValue(25)
        self.ship_count.setMaximumWidth(160)
        controls_grid.addWidget(self.ship_count, 1, 0)

        self.prepare_button = command_button("Подготовить выбранную", tone="primary", parent=controls)
        self.prepare_button.clicked.connect(self.prepare_selected)
        controls_grid.addWidget(self.prepare_button, 1, 1)

        self.send_button = command_button("Отправить выбранную", tone="warning", parent=controls)
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.setProperty("tone", "warning")
        self.send_button.clicked.connect(self.send_selected)
        controls_grid.addWidget(self.send_button, 1, 2)
        controls_grid.setColumnStretch(3, 1)
        controls.content_layout.addLayout(controls_grid)

        self.action_banner = StateBanner(
            "Ожидание выбора",
            "Выбери queued-строку. Действия доступны только при включённом V2 action gate.",
            tone="info",
            parent=controls,
        )
        self.action_status = self.action_banner.detail
        self.action_status.setText("Выбери строку очереди.")
        controls.content_layout.addWidget(self.action_banner)
        self.layout().insertWidget(2, controls)
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

    def _refill_preview(self):
        previewer = getattr(self.context, "preview_queue_refill", None)
        if not callable(previewer):
            raise RuntimeError("V2 queue refill policy недоступен")
        mode = str(self.queue_mode.currentData())
        return previewer(
            mode=mode,
            queue_size=self.queue_size.value(),
            minimum_metal=self.minimum_metal.value(),
        )

    @staticmethod
    def _preview_text(preview) -> str:
        skipped_preview = ", ".join(
            f"{item.coord}:{item.reason.value}" for item in preview.skipped[:8]
        ) or "—"
        return (
            f"Режим: {preview.mode}\n"
            f"Итоговая queued: {len(preview.desired)}\n"
            f"Добавить: {len(preview.added)} · оставить: {len(preview.kept)} · убрать replaceable: {len(preview.removed)}\n"
            f"Protected sending/sent/ambiguous: {len(preview.protected)}\n"
            f"Пропущено: {len(preview.skipped)}\n\n"
            f"Первые skip: {skipped_preview}"
        )

    def preview_refill(self) -> None:
        try:
            preview = self._refill_preview()
        except Exception as exc:
            self.refill_status.setText(f"Предпросмотр остановлен: {exc}")
            return
        self.refill_status.setText(
            f"add {len(preview.added)} · keep {len(preview.kept)} · remove {len(preview.removed)} · "
            f"protected {len(preview.protected)} · skip {len(preview.skipped)}"
        )
        QMessageBox.information(self, "Предпросмотр V2-очереди", self._preview_text(preview))

    def apply_refill(self) -> None:
        applier = getattr(self.context, "apply_queue_refill", None)
        if not callable(applier):
            self.refill_status.setText("V2 queue refill persistence недоступен.")
            return
        try:
            # Recalculate immediately before apply so a stale UI preview is never trusted.
            preview = self._refill_preview()
        except Exception as exc:
            self.refill_status.setText(f"Пересборка остановлена: {exc}")
            return
        answer = QMessageBox.question(
            self,
            "Пересобрать V2-очередь",
            self._preview_text(preview) + "\n\nProtected строки не изменяются. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = applier(preview)
        except Exception as exc:
            self.refill_status.setText(f"Пересборка остановлена: {exc}")
            return
        self.reload_view()
        self.refill_status.setText(
            f"V2-очередь: created {result.created} · updated {result.updated} · removed {result.removed}; "
            f"protected {len(preview.protected)}"
        )

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

    def _actionable_item(self, title: str) -> QueueSnapshot | None:
        item = self._selected_item()
        if item is None:
            return None
        if item.state != "queued":
            QMessageBox.warning(self, title, f"Строка имеет состояние «{item.state}», а не queued.")
            return None
        if not item.enabled:
            QMessageBox.warning(self, title, f"Цель {item.coord} выключена и не может быть отправлена.")
            return None
        if item.blacklisted:
            QMessageBox.warning(self, title, f"Цель {item.coord} находится в blacklist.")
            return None
        return item

    def prepare_selected(self) -> None:
        item = self._actionable_item("Подготовка")
        if item is None:
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
        item = self._actionable_item("Отправка")
        if item is None:
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
