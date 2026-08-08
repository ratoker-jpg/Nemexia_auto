from __future__ import annotations

import uuid

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class ReconPage(FilterableReadOnlyTable):
    """V2-owned reconnaissance plus explicit, confirmed one-shot spy processing."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        self.context = context
        super().__init__(
            ("Отчёт", "Report ID", "Координаты", "Энергия", "Металл", "Минералы", "Газ", "Источник", "Принят V2"),
            self._rows(),
            placeholder="Поиск по V2-разведке…",
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
        self.ingest_button = QPushButton("Принять свежие отчёты", action)
        self.ingest_button.setObjectName("IngestReconButton")
        self.status_label = QLabel(
            "V2 хранит только свежие отчёты с точным report ID, целью и временем",
            action,
        )
        self.status_label.setWordWrap(True)
        row.addWidget(label)
        row.addWidget(self.fleet_id)
        row.addWidget(self.process_button)
        row.addWidget(self.ingest_button)
        row.addWidget(self.status_label, 1)
        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, action)
        self.process_button.clicked.connect(self._process_selected_spy)
        self.ingest_button.clicked.connect(lambda: self._ingest_live())

    def _rows(self) -> list[tuple[object, ...]]:
        return [
            (
                item.report_at,
                item.report_id,
                item.target_coord,
                item.energy,
                item.metal,
                item.minerals,
                item.gas,
                item.source,
                item.ingested_at,
            )
            for item in self.context.recon()
        ]

    def _refresh_rows(self) -> None:
        self.model.replace_rows(self._rows())

    def _ingest_live(self, *, notify: bool = True) -> bool:
        ingest = getattr(self.context, "ingest_live_recon", None)
        if not callable(ingest):
            if notify:
                QMessageBox.critical(self, "Разведка", "V2 recon storage недоступен.")
            return False
        try:
            result = ingest()
        except Exception as exc:
            self.status_label.setText(f"Разведка не принята: {exc}")
            if notify:
                QMessageBox.warning(self, "Разведка не принята", str(exc))
            return False
        self._refresh_rows()
        self.status_label.setText(
            f"V2 recon: новых {result.inserted}, дублей {result.duplicates}, "
            f"partial {result.rejected_partial}, stale {result.rejected_stale}"
        )
        if notify:
            QMessageBox.information(
                self,
                "V2-разведка обновлена",
                f"Новых снимков: {result.inserted}\nДубликатов: {result.duplicates}\n"
                f"Отклонено partial: {result.rejected_partial}\nОтклонено stale: {result.rejected_stale}",
            )
        return True

    def _process_selected_spy(self) -> None:
        fleet_id = self.fleet_id.text().strip()
        if not fleet_id:
            QMessageBox.warning(self, "Разведка", "Укажи fleet ID существующего шпионского полёта на fleets.php.")
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
            ingested = self._ingest_live(notify=False)
            suffix = " · сохранено в V2" if ingested else " · V2 ingestion остановлен"
            self.status_label.setText(
                f"Проверено: fleet {result.fleet_id} → {result.target}, report {result.report_id}{suffix}"
            )
            QMessageBox.information(
                self,
                "Разведка подтверждена",
                f"Новый отчёт {result.report_id} подтверждён для цели {result.target}.{suffix}",
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
