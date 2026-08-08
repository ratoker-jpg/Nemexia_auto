from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from v2.application.context import V2ApplicationContext
from v2.application.debris_workflow import DebrisPreparationBatch, DebrisWorkflowState
from v2.domain.debris import DebrisReadState
from v2.domain.debris_candidates import DebrisCandidate
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class DebrisPage(FilterableReadOnlyTable):
    """V2-owned debris evidence plus explicit bounded manual recycling workflow."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        self.context = context
        self._candidates: tuple[DebrisCandidate, ...] = ()
        self._prepared_batch: DebrisPreparationBatch | None = None
        self._series_running = False
        super().__init__(
            (
                "Текущая цель",
                "Evidence coord",
                "Наблюдалось",
                "След. движение",
                "Период, сек",
                "Сдвигов",
                "Debris marker",
                "Источник evidence",
            ),
            (),
            placeholder="Поиск по debris candidates…",
            parent=parent,
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        controls = QWidget(self)
        controls.setObjectName("DebrisControls")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(QLabel("Источник", controls))
        self.source_coord = QLineEdit(controls)
        self.source_coord.setObjectName("DebrisSourceCoord")
        self.source_coord.setPlaceholderText("g:s:p")
        self.source_coord.setMaximumWidth(110)
        self.source_coord.setText(str(context.v2_setting("farm_home", "")))
        action_row.addWidget(self.source_coord)

        action_row.addWidget(QLabel("Переработчиков", controls))
        self.recycler_count = QSpinBox(controls)
        self.recycler_count.setObjectName("DebrisRecyclerCount")
        self.recycler_count.setRange(1, 100000)
        try:
            legacy_recyclers = int(
                str(context.legacy_setting("debris_recyclers", "100") or "100")
            )
        except ValueError:
            legacy_recyclers = 100
        self.recycler_count.setValue(max(1, legacy_recyclers))
        action_row.addWidget(self.recycler_count)

        action_row.addWidget(QLabel("Safety, сек", controls))
        self.safety_seconds = QSpinBox(controls)
        self.safety_seconds.setObjectName("DebrisSafetySeconds")
        self.safety_seconds.setRange(0, 3600)
        try:
            legacy_safety = int(
                str(context.legacy_setting("asteroid_safety_seconds", "10") or "10")
            )
        except ValueError:
            legacy_safety = 10
        self.safety_seconds.setValue(max(0, legacy_safety))
        action_row.addWidget(self.safety_seconds)

        self.read_button = QPushButton("Прочитать открытую систему", controls)
        self.read_button.setObjectName("ReadDebrisButton")
        self.prepare_button = QPushButton("Подготовить выбранные", controls)
        self.prepare_button.setObjectName("PrepareDebrisButton")
        self.confirm_button = QPushButton("Подтвердить отправку", controls)
        self.confirm_button.setObjectName("ConfirmDebrisButton")
        self.confirm_button.setEnabled(False)
        self.stop_button = QPushButton("Остановить серию", controls)
        self.stop_button.setObjectName("StopDebrisButton")
        self.stop_button.setEnabled(False)
        action_row.addWidget(self.read_button)
        action_row.addWidget(self.prepare_button)
        action_row.addWidget(self.confirm_button)
        action_row.addWidget(self.stop_button)
        action_row.addStretch(1)
        controls_layout.addLayout(action_row)

        self.status_label = QLabel(
            "Открой нужную galaxy.php систему вручную. V2 читает только её и не выполняет автоматический обход 3×40.",
            controls,
        )
        self.status_label.setObjectName("DebrisStatus")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, controls)

        self.read_button.clicked.connect(self._read_current_system)
        self.prepare_button.clicked.connect(self._prepare_selected)
        self.confirm_button.clicked.connect(self._confirm_dispatch)
        self.stop_button.clicked.connect(self._request_manual_stop)
        self.source_coord.textChanged.connect(self._invalidate_preparation)
        self.recycler_count.valueChanged.connect(self._invalidate_preparation)
        self.safety_seconds.valueChanged.connect(self._invalidate_preparation)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(lambda *_args: self._invalidate_preparation())
        self.reload_view()

    def hideEvent(self, event) -> None:
        if self._series_running:
            self._request_manual_stop()
        else:
            self._invalidate_preparation()
        super().hideEvent(event)

    def _rows(self) -> list[tuple[object, ...]]:
        return [
            (
                candidate.current_coord,
                candidate.observation.coord,
                candidate.observation.asteroid.observed_at,
                candidate.observation.asteroid.next_move_at,
                candidate.observation.asteroid.period_seconds,
                candidate.shifts,
                candidate.observation.marker,
                candidate.observation.source,
            )
            for candidate in self._candidates
        ]

    def reload_view(self) -> None:
        preview = getattr(self.context, "debris_candidates", None)
        if not callable(preview):
            self._candidates = ()
            self.model.replace_rows(())
            self._invalidate_preparation()
            if hasattr(self, "status_label"):
                self.status_label.setText("V2 debris evidence/candidate services недоступны")
            return
        try:
            result = preview()
        except Exception as exc:
            self._candidates = ()
            self.model.replace_rows(())
            self._invalidate_preparation()
            if hasattr(self, "status_label"):
                self.status_label.setText(f"Debris candidate preview недоступен: {exc}")
            return
        self._candidates = tuple(result.candidates)
        self.model.replace_rows(self._rows())
        self._invalidate_preparation()
        if hasattr(self, "status_label"):
            gate = "ON" if getattr(self.context, "debris_actions_enabled", lambda: False)() else "OFF"
            self.status_label.setText(
                f"V2 debris candidates: {len(self._candidates)} · actions_enabled={gate} · "
                "evidence накапливается между вручную открытыми системами"
            )

    def _read_current_system(self) -> None:
        reader = getattr(self.context, "live_debris", None)
        ingest = getattr(self.context, "ingest_debris_read", None)
        if not callable(reader) or not callable(ingest):
            QMessageBox.critical(self, "Обломки", "V2 debris read/storage services недоступны.")
            return
        try:
            snapshot = reader()
        except Exception as exc:
            self.status_label.setText(f"Debris read остановлен: {exc}")
            QMessageBox.warning(self, "Debris read остановлен", str(exc))
            return

        if snapshot.state is DebrisReadState.CAPTCHA:
            self.status_label.setText("CAPTCHA: debris read остановлен; требуется ручное действие")
            QMessageBox.warning(self, "CAPTCHA", snapshot.detail)
            return
        if snapshot.state is DebrisReadState.LIVE_UNAVAILABLE:
            self.status_label.setText(f"Live debris source недоступен: {snapshot.detail}")
            QMessageBox.warning(self, "Debris source недоступен", snapshot.detail)
            return
        if snapshot.state is DebrisReadState.PARTIAL_EVIDENCE:
            self.status_label.setText(
                "Partial/unreadable debris evidence: текущая система не считается доказанно пустой"
            )
            QMessageBox.warning(self, "Неполное evidence", snapshot.detail)
            return

        try:
            result = ingest(snapshot)
        except Exception as exc:
            self.status_label.setText(f"Debris ingestion остановлен: {exc}")
            QMessageBox.warning(self, "Debris ingestion остановлен", str(exc))
            return
        self.reload_view()

        if snapshot.state is DebrisReadState.NO_DEBRIS:
            self.status_label.setText(
                "В текущей вручную открытой системе debris не доказан. Ранее сохранённое evidence других систем не очищено."
            )
            QMessageBox.information(self, "Обломки", snapshot.detail)
            return

        self.status_label.setText(
            f"Current-system evidence: {len(snapshot.observations)} debris · "
            f"сохранено {result.inserted} · exact duplicates {result.exact_duplicates} · "
            f"candidates {len(result.preview.candidates)}"
        )

    def _selected_candidates(self) -> tuple[DebrisCandidate, ...]:
        selection = self.table.selectionModel()
        if selection is None:
            return ()
        source_rows = {
            self.proxy.mapToSource(index).row()
            for index in selection.selectedRows()
            if index.isValid()
        }
        return tuple(
            self._candidates[index]
            for index in sorted(source_rows)
            if 0 <= index < len(self._candidates)
        )

    def _workflow_inputs(self) -> tuple[str, int, int]:
        return (
            self.source_coord.text().strip(),
            int(self.recycler_count.value()),
            int(self.safety_seconds.value()),
        )

    def _invalidate_preparation(self, *_args) -> None:
        if self._series_running:
            return
        self._prepared_batch = None
        cancel = getattr(self.context, "cancel_debris_preparation", None)
        if callable(cancel):
            cancel()
        if hasattr(self, "confirm_button"):
            self.confirm_button.setEnabled(False)

    def _prepare_selected(self) -> None:
        selected = self._selected_candidates()
        if not selected:
            QMessageBox.warning(self, "Обломки", "Выбери хотя бы один debris candidate.")
            return
        prepare = getattr(self.context, "prepare_debris_candidates", None)
        if not callable(prepare):
            QMessageBox.critical(self, "Обломки", "V2 debris preparation workflow недоступен.")
            return
        source, recyclers, safety = self._workflow_inputs()
        try:
            batch = prepare(
                selected,
                source=source,
                recycler_count=recyclers,
                safety_seconds=safety,
            )
        except Exception as exc:
            self.status_label.setText(f"Debris preparation остановлен: {exc}")
            QMessageBox.warning(self, "Preparation остановлен", str(exc))
            return
        if batch.state is not DebrisWorkflowState.AWAITING_CONFIRMATION:
            coord = batch.stopped_candidate.current_coord if batch.stopped_candidate is not None else "—"
            self.status_label.setText(
                f"Debris preparation {batch.state.value} на {coord} после {len(batch.prepared)} ready: {batch.detail}"
            )
            title = "CAPTCHA" if batch.state is DebrisWorkflowState.STOPPED_CAPTCHA else "Preparation остановлен"
            QMessageBox.warning(self, title, batch.detail)
            return

        self._prepared_batch = batch
        actions_enabled = getattr(self.context, "debris_actions_enabled", lambda: False)()
        self.confirm_button.setEnabled(bool(actions_enabled))
        targets = ", ".join(item.preparation.target for item in batch.prepared[:5])
        suffix = "…" if len(batch.prepared) > 5 else ""
        self.status_label.setText(
            f"Read-only preparation READY: {len(batch.prepared)} · targets {targets}{suffix} · "
            f"explicit confirmation required · actions_enabled={'ON' if actions_enabled else 'OFF'}"
        )
        if not actions_enabled:
            QMessageBox.warning(
                self,
                "Действия отключены",
                "Preparation выполнен без mutation. Включи actions_enabled в V2 Settings для подтверждённой отправки.",
            )

    def _set_series_controls(self, running: bool) -> None:
        self._series_running = bool(running)
        for widget in (
            self.read_button,
            self.prepare_button,
            self.confirm_button,
            self.source_coord,
            self.recycler_count,
            self.safety_seconds,
            self.table,
        ):
            widget.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _request_manual_stop(self) -> None:
        if not self._series_running:
            return
        request_stop = getattr(self.context, "request_debris_stop", None)
        if callable(request_stop):
            request_stop()
        self.stop_button.setEnabled(False)
        self.status_label.setText(
            "Остановка запрошена · уже начатая remote-попытка не прерывается; следующая цель не начнётся"
        )

    def _between_attempts(self) -> None:
        # Events are processed only between completed attempts. The remote call
        # itself remains synchronous and is never cancelled from the UI.
        QApplication.processEvents()
        window = self.window()
        if not self.isVisible() or window is None or not window.isVisible():
            request_stop = getattr(self.context, "request_debris_stop", None)
            if callable(request_stop):
                request_stop()

    def _confirm_dispatch(self) -> None:
        batch = self._prepared_batch
        if batch is None or not batch.confirmation_id:
            QMessageBox.warning(self, "Обломки", "Сначала выполни read-only preparation выбранных целей.")
            return
        if not getattr(self.context, "debris_actions_enabled", lambda: False)():
            self.confirm_button.setEnabled(False)
            self.status_label.setText("actions_enabled=OFF — debris dispatch запрещён")
            QMessageBox.warning(
                self,
                "Действия отключены",
                "Включи actions_enabled в V2 Settings перед ручным подтверждением.",
            )
            return

        source, recyclers, safety = self._workflow_inputs()
        targets = ", ".join(item.preparation.target for item in batch.prepared[:8])
        suffix = "…" if len(batch.prepared) > 8 else ""
        answer = QMessageBox.question(
            self,
            "Подтвердить debris dispatch",
            (
                f"Отправить подготовленные цели: {len(batch.prepared)}?\n\n"
                f"Источник: {source}\nПереработчиков на цель: {recyclers}\nSafety: {safety} сек\n"
                f"Targets: {targets}{suffix}\n\n"
                "Каждая цель снова проходит live trajectory/recycler/capacity re-check через общий asteroid journal. "
                "Серия остановится на первой CAPTCHA, ambiguity, ошибке или ручном Stop. "
                "Автоматических повторов и автоматического обхода систем нет."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        dispatch = getattr(self.context, "confirm_debris_candidates", None)
        if not callable(dispatch):
            QMessageBox.critical(self, "Обломки", "V2 debris dispatch workflow недоступен.")
            return

        confirmation_id = batch.confirmation_id
        self._prepared_batch = None
        self._set_series_controls(True)
        self.status_label.setText(
            f"Debris series подтверждена вручную · целей {len(batch.prepared)} · Stop действует перед следующей целью"
        )
        try:
            result = dispatch(
                confirmation_id,
                between_attempts=self._between_attempts,
            )
        except Exception as exc:
            self.status_label.setText(f"Debris series остановлена: {exc}")
            QMessageBox.warning(self, "Debris series остановлена", str(exc))
            return
        finally:
            self._set_series_controls(False)
            self.confirm_button.setEnabled(False)

        if result.state is DebrisWorkflowState.COMPLETED:
            fleet_ids = ", ".join(step.result.fleet_id or "—" for step in result.completed)
            self.status_label.setText(
                f"Debris series verified: {result.verified_count}/{len(batch.prepared)} · fleet IDs {fleet_ids}"
            )
            QMessageBox.information(
                self,
                "Debris dispatch подтверждён",
                f"Проверено отправок: {result.verified_count}.\nFleet IDs: {fleet_ids}",
            )
            return

        coord = result.stopped_candidate.current_coord if result.stopped_candidate is not None else "—"
        self.status_label.setText(
            f"Debris series {result.state.value} на {coord} после {result.verified_count} verified: {result.detail}"
        )
        if result.state is DebrisWorkflowState.STOPPED_MANUAL:
            QMessageBox.information(
                self,
                "Debris series остановлена вручную",
                f"Verified до остановки: {result.verified_count}.\nСледующая цель не запускалась: {coord}",
            )
            return
        title = "CAPTCHA" if result.state is DebrisWorkflowState.STOPPED_CAPTCHA else "Debris series остановлена"
        QMessageBox.warning(self, title, result.detail)
