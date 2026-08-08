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
from v2.application.asteroid_workflow import AsteroidPreparationBatch, AsteroidWorkflowState
from v2.domain.asteroid_candidates import AsteroidCandidate
from v2.domain.asteroids import AsteroidReadState
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class AsteroidsPage(FilterableReadOnlyTable):
    """Explicit attach-only asteroid read/preview and bounded manual dispatch surface."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        self.context = context
        self._candidates: tuple[AsteroidCandidate, ...] = ()
        self._series_running = False
        self._stop_requested = False
        super().__init__(
            (
                "Текущая цель",
                "Наблюдение",
                "Наблюдалось",
                "След. движение",
                "Период, сек",
                "Сдвигов",
                "Источник evidence",
            ),
            (),
            placeholder="Поиск по asteroid candidates…",
            parent=parent,
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        controls = QWidget(self)
        controls.setObjectName("AsteroidControls")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(QLabel("Источник", controls))
        self.source_coord = QLineEdit(controls)
        self.source_coord.setObjectName("AsteroidSourceCoord")
        self.source_coord.setPlaceholderText("g:s:p")
        self.source_coord.setMaximumWidth(110)
        self.source_coord.setText(str(context.v2_setting("farm_home", "")))
        action_row.addWidget(self.source_coord)

        action_row.addWidget(QLabel("Переработчиков", controls))
        self.recycler_count = QSpinBox(controls)
        self.recycler_count.setObjectName("AsteroidRecyclerCount")
        self.recycler_count.setRange(1, 100000)
        try:
            legacy_recyclers = int(str(context.legacy_setting("asteroid_recyclers", "5") or "5"))
        except ValueError:
            legacy_recyclers = 5
        self.recycler_count.setValue(max(1, legacy_recyclers))
        action_row.addWidget(self.recycler_count)

        action_row.addWidget(QLabel("Safety, сек", controls))
        self.safety_seconds = QSpinBox(controls)
        self.safety_seconds.setObjectName("AsteroidSafetySeconds")
        self.safety_seconds.setRange(0, 3600)
        try:
            legacy_safety = int(str(context.legacy_setting("asteroid_safety_seconds", "10") or "10"))
        except ValueError:
            legacy_safety = 10
        self.safety_seconds.setValue(max(0, legacy_safety))
        action_row.addWidget(self.safety_seconds)

        self.read_button = QPushButton("Прочитать открытую систему", controls)
        self.read_button.setObjectName("ReadAsteroidsButton")
        self.prepare_button = QPushButton("Проверить выбранные", controls)
        self.prepare_button.setObjectName("PrepareAsteroidsButton")
        self.send_button = QPushButton("Отправить выбранные", controls)
        self.send_button.setObjectName("DispatchAsteroidsButton")
        self.stop_button = QPushButton("Остановить серию", controls)
        self.stop_button.setObjectName("StopAsteroidsButton")
        self.stop_button.setEnabled(False)
        action_row.addWidget(self.read_button)
        action_row.addWidget(self.prepare_button)
        action_row.addWidget(self.send_button)
        action_row.addWidget(self.stop_button)
        action_row.addStretch(1)
        controls_layout.addLayout(action_row)

        self.status_label = QLabel(
            "Открой нужную galaxy.php вручную. V2 не переключает систему и не запускает браузер.",
            controls,
        )
        self.status_label.setObjectName("AsteroidStatus")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, controls)

        self.read_button.clicked.connect(self._read_current_system)
        self.prepare_button.clicked.connect(self._prepare_selected)
        self.send_button.clicked.connect(self._dispatch_selected)
        self.stop_button.clicked.connect(self._request_manual_stop)
        self.reload_view()

    def _rows(self) -> list[tuple[object, ...]]:
        return [
            (
                candidate.current_coord,
                candidate.observation.coord,
                candidate.observation.observed_at,
                candidate.observation.next_move_at,
                candidate.observation.period_seconds,
                candidate.shifts,
                candidate.observation.source,
            )
            for candidate in self._candidates
        ]

    def reload_view(self) -> None:
        preview = getattr(self.context, "asteroid_candidates", None)
        if not callable(preview):
            self._candidates = ()
            self.model.replace_rows(())
            if hasattr(self, "status_label"):
                self.status_label.setText("V2 asteroid candidate storage недоступен")
            return
        try:
            result = preview()
        except Exception as exc:
            self._candidates = ()
            self.model.replace_rows(())
            if hasattr(self, "status_label"):
                self.status_label.setText(f"Candidate preview недоступен: {exc}")
            return
        self._candidates = tuple(result.candidates)
        self.model.replace_rows(self._rows())
        if hasattr(self, "status_label"):
            gate = "ON" if getattr(self.context, "asteroid_actions_enabled", lambda: False)() else "OFF"
            self.status_label.setText(
                f"V2 candidates: {len(self._candidates)} · actions_enabled={gate} · "
                "выбор и порядок основаны на typed candidate state"
            )

    def _read_current_system(self) -> None:
        reader = getattr(self.context, "live_asteroids", None)
        ingest = getattr(self.context, "ingest_asteroid_observations", None)
        if not callable(reader) or not callable(ingest):
            QMessageBox.critical(self, "Астероиды", "V2 asteroid read/storage services недоступны.")
            return
        try:
            snapshot = reader()
        except Exception as exc:
            self.status_label.setText(f"Asteroid read остановлен: {exc}")
            QMessageBox.warning(self, "Asteroid read остановлен", str(exc))
            return

        if snapshot.state is AsteroidReadState.CAPTCHA:
            self.status_label.setText("CAPTCHA: asteroid read остановлен; требуется ручное действие")
            QMessageBox.warning(self, "CAPTCHA", snapshot.detail)
            return
        if snapshot.state is AsteroidReadState.LIVE_UNAVAILABLE:
            self.status_label.setText(f"Live asteroid source недоступен: {snapshot.detail}")
            QMessageBox.warning(self, "Asteroid source недоступен", snapshot.detail)
            return
        if snapshot.state is AsteroidReadState.NO_ASTEROIDS:
            self.status_label.setText("В уже открытой системе астероиды не найдены; V2 state не очищен")
            QMessageBox.information(self, "Астероиды", snapshot.detail)
            return

        try:
            result = ingest(snapshot.observations)
        except Exception as exc:
            self.status_label.setText(f"Asteroid ingestion остановлен: {exc}")
            QMessageBox.warning(self, "Asteroid ingestion остановлен", str(exc))
            return
        self.reload_view()
        self.status_label.setText(
            f"Прочитано {len(snapshot.observations)} · сохранено {result.inserted} · "
            f"exact duplicates {result.exact_duplicates} · candidates {len(result.preview.candidates)}"
        )

    def _selected_candidates(self) -> tuple[AsteroidCandidate, ...]:
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

    def _prepare_batch(self, selected: tuple[AsteroidCandidate, ...]) -> AsteroidPreparationBatch | None:
        if not selected:
            QMessageBox.warning(self, "Астероиды", "Выбери хотя бы один asteroid candidate.")
            return None
        prepare = getattr(self.context, "prepare_asteroid_candidates", None)
        if not callable(prepare):
            QMessageBox.critical(self, "Астероиды", "V2 asteroid preparation workflow недоступен.")
            return None
        source, recyclers, safety = self._workflow_inputs()
        try:
            return prepare(
                selected,
                source=source,
                recycler_count=recyclers,
                safety_seconds=safety,
            )
        except Exception as exc:
            self.status_label.setText(f"Preparation остановлен: {exc}")
            QMessageBox.warning(self, "Preparation остановлен", str(exc))
            return None

    def _show_preparation_stop(self, batch: AsteroidPreparationBatch) -> None:
        coord = batch.stopped_candidate.current_coord if batch.stopped_candidate is not None else "—"
        self.status_label.setText(
            f"Preparation {batch.state.value} на {coord} после {len(batch.prepared)} ready: {batch.detail}"
        )
        title = "CAPTCHA" if batch.state is AsteroidWorkflowState.STOPPED_CAPTCHA else "Preparation остановлен"
        QMessageBox.warning(self, title, batch.detail)

    def _prepare_selected(self) -> None:
        batch = self._prepare_batch(self._selected_candidates())
        if batch is None:
            return
        if batch.state is not AsteroidWorkflowState.READY:
            self._show_preparation_stop(batch)
            return
        targets = ", ".join(item.preparation.target for item in batch.prepared[:5])
        suffix = "…" if len(batch.prepared) > 5 else ""
        self.status_label.setText(
            f"Read-only preparation READY: {len(batch.prepared)} · targets {targets}{suffix}"
        )
        QMessageBox.information(
            self,
            "Asteroid preparation готов",
            f"Без game mutation проверено: {len(batch.prepared)}.\nTargets: {targets}{suffix}",
        )

    def _set_series_controls(self, running: bool) -> None:
        self._series_running = bool(running)
        for widget in (
            self.read_button,
            self.prepare_button,
            self.send_button,
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
        self._stop_requested = True
        self.stop_button.setEnabled(False)
        self.status_label.setText(
            "Остановка запрошена · текущая SendFleet-попытка не прерывается; следующая цель не начнётся"
        )

    def _poll_manual_stop(self) -> bool:
        # The remote attempt itself stays synchronous and atomic. Event delivery is
        # permitted only between completed attempts so Stop can block the next one.
        QApplication.processEvents()
        return bool(self._stop_requested)

    def _dispatch_selected(self) -> None:
        selected = self._selected_candidates()
        batch = self._prepare_batch(selected)
        if batch is None:
            return
        if batch.state is not AsteroidWorkflowState.READY:
            self._show_preparation_stop(batch)
            return

        if not getattr(self.context, "asteroid_actions_enabled", lambda: False)():
            self.status_label.setText("actions_enabled=OFF — asteroid dispatch запрещён")
            QMessageBox.warning(
                self,
                "Действия отключены",
                "Включи actions_enabled в V2 Settings перед ручной отправкой.",
            )
            return

        source, recyclers, safety = self._workflow_inputs()
        answer = QMessageBox.question(
            self,
            "Подтвердить asteroid dispatch",
            (
                f"Отправить выбранные цели: {len(selected)}?\n\n"
                f"Источник: {source}\nПереработчиков на цель: {recyclers}\nSafety: {safety} сек\n\n"
                "Каждая цель снова проходит live re-check и persistent journal перед SendFleet. "
                "Серия остановится на первой CAPTCHA, ambiguity, ошибке или ручном Stop. "
                "Уже начатая попытка не отменяется и автоматических повторов нет."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        dispatch = getattr(self.context, "dispatch_asteroid_candidates", None)
        if not callable(dispatch):
            QMessageBox.critical(self, "Астероиды", "V2 asteroid dispatch workflow недоступен.")
            return

        self._stop_requested = False
        self._set_series_controls(True)
        self.status_label.setText(
            f"Asteroid series запущена вручную · выбрано {len(selected)} · Stop действует перед следующей целью"
        )
        try:
            result = dispatch(
                selected,
                source=source,
                recycler_count=recyclers,
                safety_seconds=safety,
                should_stop=self._poll_manual_stop,
            )
        except Exception as exc:
            self.status_label.setText(f"Asteroid series остановлена: {exc}")
            QMessageBox.warning(self, "Asteroid series остановлена", str(exc))
            return
        finally:
            self._set_series_controls(False)

        if result.state is AsteroidWorkflowState.COMPLETED:
            fleet_ids = ", ".join(step.result.fleet_id or "—" for step in result.completed)
            self.status_label.setText(
                f"Asteroid series verified: {result.verified_count}/{len(selected)} · fleet IDs {fleet_ids}"
            )
            QMessageBox.information(
                self,
                "Asteroid dispatch подтверждён",
                f"Проверено отправок: {result.verified_count}.\nFleet IDs: {fleet_ids}",
            )
            return

        coord = result.stopped_candidate.current_coord if result.stopped_candidate is not None else "—"
        self.status_label.setText(
            f"Asteroid series {result.state.value} на {coord} после {result.verified_count} verified: {result.detail}"
        )
        if result.state is AsteroidWorkflowState.STOPPED_MANUAL:
            QMessageBox.information(
                self,
                "Asteroid series остановлена вручную",
                f"Verified до остановки: {result.verified_count}.\nСледующая цель не запускалась: {coord}",
            )
            return
        QMessageBox.warning(
            self,
            "Asteroid series остановлена",
            f"{result.state.value}\nПосле verified: {result.verified_count}\n{result.detail}",
        )
