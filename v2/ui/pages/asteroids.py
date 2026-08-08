from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from v2.application.asteroid_actions import AsteroidActionError, AsteroidDispatchPreparation
from v2.application.asteroid_repository import AsteroidIngestResult
from v2.domain.asteroid_candidates import AsteroidCandidate, AsteroidCandidatePreview
from v2.domain.asteroids import ASTEROID_DEFAULT_SAFETY_SECONDS, AsteroidReadState


class AsteroidsPage(QWidget):
    """Explicit, bounded V2 asteroid workflow. No timers or automatic repeat."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._last_live = ()
        self._last_live_now: datetime | None = None
        self._candidates: tuple[AsteroidCandidate, ...] = ()
        self._prepared: AsteroidDispatchPreparation | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Астероиды")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        help_text = QLabel(
            "Attach-only: вручную открой нужную galaxy.php систему и fleets.php. "
            "V2 не переключает планету/систему и не повторяет неоднозначную отправку."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        controls = QGroupBox("Управляемый цикл")
        controls_layout = QFormLayout(controls)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Источник G:S:P")
        controls_layout.addRow("Планета-источник", self.source_edit)

        self.recycler_spin = QSpinBox()
        self.recycler_spin.setRange(1, 1_000_000)
        self.recycler_spin.setValue(5)
        controls_layout.addRow("Переработчики", self.recycler_spin)

        self.safety_spin = QSpinBox()
        self.safety_spin.setRange(0, 3600)
        self.safety_spin.setValue(ASTEROID_DEFAULT_SAFETY_SECONDS)
        self.safety_spin.setSuffix(" сек")
        controls_layout.addRow("Буфер движения", self.safety_spin)
        layout.addWidget(controls)

        row = QHBoxLayout()
        self.read_button = QPushButton("Прочитать текущую систему")
        self.read_button.clicked.connect(self._read_live)
        row.addWidget(self.read_button)
        self.ingest_button = QPushButton("Сохранить подтверждённые")
        self.ingest_button.setEnabled(False)
        self.ingest_button.clicked.connect(self._ingest_live)
        row.addWidget(self.ingest_button)
        self.refresh_button = QPushButton("Обновить кандидатов")
        self.refresh_button.clicked.connect(self._refresh_candidates)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QLabel("Готово. Автоматические действия не запущены.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Текущая цель", "Origin", "Сдвигов", "Наблюдение UTC", "Источник", "Состояние"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        self.prepare_button = QPushButton("Prepare")
        self.prepare_button.setEnabled(False)
        self.prepare_button.clicked.connect(self._prepare_selected)
        action_row.addWidget(self.prepare_button)
        self.dispatch_button = QPushButton("Отправить выбранный астероид")
        self.dispatch_button.setEnabled(False)
        self.dispatch_button.clicked.connect(self._dispatch_selected)
        action_row.addWidget(self.dispatch_button)
        self.gate_label = QLabel()
        action_row.addWidget(self.gate_label)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self._refresh_gate()
        self._refresh_candidates()

    def _refresh_gate(self) -> None:
        enabled = bool(self.context.asteroid_actions_enabled())
        self.gate_label.setText("Action gate: ВКЛ" if enabled else "Action gate: ВЫКЛ")
        self.dispatch_button.setEnabled(enabled and self._selected_candidate() is not None)

    def _operation_error(self, prefix: str, exc: Exception) -> None:
        self._prepared = None
        self.status_label.setText(f"{prefix}: {exc}")
        self._refresh_gate()

    def _read_live(self) -> None:
        self._prepared = None
        try:
            snapshot = self.context.live_asteroids()
        except Exception as exc:
            self._operation_error("Live asteroid read недоступен", exc)
            return
        if snapshot.state is AsteroidReadState.CAPTCHA:
            self._last_live = ()
            self.ingest_button.setEnabled(False)
            self.status_label.setText("CAPTCHA обнаружена. Пройди её вручную; V2 ничего не кликает.")
            return
        if snapshot.state is AsteroidReadState.LIVE_UNAVAILABLE:
            self._last_live = ()
            self.ingest_button.setEnabled(False)
            self.status_label.setText(snapshot.detail or "Открой нужную galaxy.php систему вручную.")
            return
        self._last_live = tuple(snapshot.observations)
        self._last_live_now = max(
            (item.observed_at for item in self._last_live),
            default=datetime.now(timezone.utc),
        )
        self.ingest_button.setEnabled(bool(self._last_live))
        if snapshot.state is AsteroidReadState.NO_ASTEROIDS:
            self.status_label.setText("Текущая открытая система прочитана: астероидов нет.")
        else:
            preview = self.context.preview_asteroids(self._last_live, now=self._last_live_now)
            self._render_preview(preview)
            self.status_label.setText(
                f"Live read: {len(self._last_live)} · preview add={preview.added}, "
                f"keep={preview.kept}, skip={preview.skipped}. Сохранение ещё не выполнено."
            )

    def _ingest_live(self) -> None:
        if not self._last_live:
            return
        now = self._last_live_now or datetime.now(timezone.utc)
        try:
            result: AsteroidIngestResult = self.context.ingest_asteroids(self._last_live, now=now)
        except Exception as exc:
            self._operation_error("Не удалось сохранить asteroid observations", exc)
            return
        self._last_live = ()
        self.ingest_button.setEnabled(False)
        self._render_preview(self.context.asteroid_candidates(now=now))
        self.status_label.setText(
            f"V2-owned observations: добавлено {result.inserted}; "
            f"exact duplicates {result.exact_duplicates}."
        )

    def _refresh_candidates(self) -> None:
        try:
            preview = self.context.asteroid_candidates(now=datetime.now(timezone.utc))
        except Exception as exc:
            self._operation_error("Candidate state недоступен", exc)
            return
        self._render_preview(preview)
        self._refresh_gate()

    def _render_preview(self, preview: AsteroidCandidatePreview) -> None:
        self._candidates = tuple(preview.candidates)
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            fact = candidate.observation
            values = (
                candidate.current_coord,
                fact.coord,
                str(candidate.shifts),
                fact.observed_at.astimezone(timezone.utc).isoformat(),
                fact.source,
                "V2-owned" if candidate.persisted else "preview",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._selection_changed()

    def _selected_candidate(self) -> AsteroidCandidate | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if len(rows) != 1:
            return None
        index = rows[0].row()
        if not 0 <= index < len(self._candidates):
            return None
        return self._candidates[index]

    def _selection_changed(self) -> None:
        selected = self._selected_candidate()
        self._prepared = None
        self.prepare_button.setEnabled(selected is not None)
        self._refresh_gate()

    def _action_inputs(self) -> tuple[str, int, int]:
        source = self.source_edit.text().strip().replace("-", ":")
        if not source:
            raise AsteroidActionError("Укажи планету-источник G:S:P")
        return source, int(self.recycler_spin.value()), int(self.safety_spin.value())

    def _prepare_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        try:
            source, recycler_count, safety_seconds = self._action_inputs()
            prepared = self.context.prepare_asteroid(
                source=source,
                observation=candidate.observation,
                recycler_count=recycler_count,
                safety_seconds=safety_seconds,
            )
        except Exception as exc:
            self._operation_error("Prepare остановлен", exc)
            return
        self._prepared = prepared
        self.status_label.setText(
            f"Prepared: {prepared.source} → {prepared.target}; recyclers={prepared.recycler_count}; "
            f"one-way={prepared.one_way_seconds}s; margin={prepared.movement_margin_seconds:.1f}s. "
            "Это ещё не отправка."
        )
        self._refresh_gate()

    def _dispatch_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        try:
            source, recycler_count, safety_seconds = self._action_inputs()
        except Exception as exc:
            self._operation_error("Отправка не начата", exc)
            return
        if not self.context.asteroid_actions_enabled():
            self._operation_error("Отправка не начата", AsteroidActionError("actions_enabled выключен"))
            return
        answer = QMessageBox.question(
            self,
            "Подтвердить отправку",
            f"Одна попытка SendFleet.\n\nИсточник: {source}\n"
            f"Asteroid evidence: {candidate.observation.coord}\n"
            f"Текущая прогнозная цель: {candidate.current_coord}\n"
            f"Переработчики: {recycler_count}\n\n"
            "При неоднозначном результате автоматического повтора НЕ будет. Отправить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status_label.setText("Отправка отменена пользователем.")
            return
        request_id = f"asteroid-{uuid4().hex}"
        self.dispatch_button.setEnabled(False)
        try:
            result = self.context.dispatch_asteroid(
                source=source,
                observation=candidate.observation,
                recycler_count=recycler_count,
                safety_seconds=safety_seconds,
                request_id=request_id,
            )
        except Exception as exc:
            self._operation_error(f"Request {request_id} остановлен", exc)
            return
        self.status_label.setText(
            f"Verified: request={request_id} · fleet={result.fleet_id} · "
            f"{result.source} → {result.target}."
        )
        self._prepared = None
        self._refresh_gate()
