from __future__ import annotations

import uuid

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class ReconPage(FilterableReadOnlyTable):
    """Persisted reconnaissance plus one explicit, confirmed spy-fleet action."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        self.context = context
        reports = context.recon()
        rows = [
            (
                item.report_at,
                item.target_coord,
                item.energy,
                item.metal,
                item.minerals,
                item.gas,
                item.population,
                item.ships,
                item.defense,
                item.completeness,
                item.source,
            )
            for item in reports
        ]
        super().__init__(
            (
                "Отчёт", "Координаты", "Энергия", "Металл", "Минералы", "Газ",
                "Население", "Корабли", "Защита", "Полнота", "Источник",
            ),
            rows,
            placeholder="Поиск по сохранённой разведке…",
            parent=parent,
        )

        action = QWidget(self)
        action.setObjectName("ReconSpyAction")
        row = QHBoxLayout(action)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = QLabel("Spy fleet ID", action)
        self.fleet_id = QLineEdit(action)
        self.fleet_id.setObjectName("SpyFleetId")
        self.fleet_id.setPlaceholderText("Например: 152272")
        self.fleet_id.setMaximumWidth(180)
        self.process_button = QPushButton("Проверить и обработать", action)
        self.process_button.setObjectName("ProcessSpyButton")
        self.status_label = QLabel(
            "Только вручную · нужен actions_enabled · fleets.php + системные сообщения должны быть открыты",
            action,
        )
        self.status_label.setWordWrap(True)
        row.addWidget(label)
        row.addWidget(self.fleet_id)
        row.addWidget(self.process_button)
        row.addWidget(self.status_label, 1)
        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, action)
        self.process_button.clicked.connect(self._process_selected_spy)

    def _process_selected_spy(self) -> None:
        fleet_id = self.fleet_id.text().strip()
        if not fleet_id:
            QMessageBox.warning(self, "Разведка", "Укажи fleet ID из раздела «Шпионажи» на fleets.php.")
            return
        prepare = getattr(self.context, "prepare_spy", None)
        process = getattr(self.context, "process_spy", None)
        if not callable(prepare) or not callable(process):
            QMessageBox.critical(self, "Разведка", "V2 spy action service недоступен.")
            return
        try:
            facts = prepare(fleet_id)
        except Exception as exc:
            QMessageBox.warning(self, "Разведка остановлена", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Подтвердить разведку",
            (
                f"Обработать spy fleet {facts.fleet_id}?\n\n"
                f"Откуда: {facts.source}\nЦель: {facts.target}\n\n"
                "Будет выполнена ровно одна попытка processSpy. При неоднозначном результате повтор запрещён."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        request_id = f"spy-{uuid.uuid4().hex}"
        try:
            result = process(facts.fleet_id, request_id=request_id)
        except Exception as exc:
            self.status_label.setText(f"Остановлено: {exc}")
            QMessageBox.warning(self, "Разведка остановлена", str(exc))
            return

        if result.verified:
            self.status_label.setText(
                f"Проверено: fleet {result.fleet_id} → {result.target}, report {result.report_id}"
            )
            QMessageBox.information(
                self,
                "Разведка подтверждена",
                f"Новый отчёт {result.report_id} подтверждён для цели {result.target}.",
            )
        else:
            self.status_label.setText(
                f"Неоднозначно: fleet {result.fleet_id} → {result.target}; автоматический повтор запрещён"
            )
            QMessageBox.warning(
                self,
                "Разведка неоднозначна",
                "Новый exact-target отчёт не подтверждён. Не повторяй действие автоматически.",
            )
