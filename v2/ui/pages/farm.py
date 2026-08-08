from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from v2.application.context import V2ApplicationContext
from v2.application.farm_controller import FarmSnapshot, FarmState


class FarmPage(QWidget):
    """Typed farm state plus an explicitly confirmed one-wave executor."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._snapshot: FarmSnapshot | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        status_card = QFrame(self)
        status_card.setObjectName("InfoCard")
        grid = QGridLayout(status_card)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)
        title = QLabel("Состояние автофарма V2", status_card)
        title.setObjectName("SectionTitle")
        grid.addWidget(title, 0, 0, 1, 2)
        self.state_value = QLabel("Не проверено", status_card)
        self.state_value.setObjectName("StatusBadge")
        self.detail_value = QLabel("Нажми «Проверить готовность».", status_card)
        self.detail_value.setObjectName("Muted")
        self.detail_value.setWordWrap(True)
        self.metrics_value = QLabel("Цели — · slots — · blocking — · unresolved —", status_card)
        self.metrics_value.setObjectName("Muted")
        grid.addWidget(QLabel("State", status_card), 1, 0)
        grid.addWidget(self.state_value, 1, 1)
        grid.addWidget(self.detail_value, 2, 0, 1, 2)
        grid.addWidget(self.metrics_value, 3, 0, 1, 2)
        layout.addWidget(status_card)

        controls = QFrame(self)
        controls.setObjectName("InfoCard")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 16)
        controls_layout.setSpacing(10)
        controls_title = QLabel("Одна волна", controls)
        controls_title.setObjectName("SectionTitle")
        controls_layout.addWidget(controls_title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Мегатранспортировщиков", controls))
        self.ship_count = QSpinBox(controls)
        self.ship_count.setRange(1, 100000)
        self.ship_count.setValue(25)
        row.addWidget(self.ship_count)
        row.addWidget(QLabel("Макс. целей", controls))
        self.max_targets = QSpinBox(controls)
        self.max_targets.setRange(1, 1000)
        self.max_targets.setValue(15)
        row.addWidget(self.max_targets)
        self.check_button = QPushButton("Проверить готовность", controls)
        self.check_button.setObjectName("SecondaryButton")
        self.check_button.clicked.connect(self.check_ready)
        row.addWidget(self.check_button)
        self.wave_button = QPushButton("Выполнить одну волну", controls)
        self.wave_button.setObjectName("PrimaryButton")
        self.wave_button.clicked.connect(self.run_wave)
        row.addWidget(self.wave_button)
        row.addStretch(1)
        controls_layout.addLayout(row)

        note = QLabel(
            "#70 не запускает непрерывный таймер: каждая волна требует явного подтверждения. "
            "При pending/ambiguous отправке волна немедленно блокируется и автоматический повтор запрещён.",
            controls,
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        controls_layout.addWidget(note)
        self.result_label = QLabel("", controls)
        self.result_label.setObjectName("Muted")
        self.result_label.setWordWrap(True)
        controls_layout.addWidget(self.result_label)
        layout.addWidget(controls)
        layout.addStretch(1)
        self.reload_view()

    def reload_view(self) -> None:
        self._render(self.context.farm_snapshot())

    def check_ready(self) -> None:
        self._set_busy(True)
        try:
            status = self.context.refresh_live_source()
            if status.available:
                self.context.reconcile_raid_actions()
            snapshot = self.context.farm_snapshot()
        except Exception as exc:
            self.result_label.setText(f"Проверка остановлена: {exc}")
            snapshot = None
        finally:
            self._set_busy(False)
        if snapshot is not None:
            self._render(snapshot)

    def run_wave(self) -> None:
        self.check_ready()
        snapshot = self._snapshot
        if snapshot is None or snapshot.state is not FarmState.READY:
            QMessageBox.warning(
                self,
                "Автофарм V2",
                snapshot.detail if snapshot is not None else "Нет актуального farm snapshot.",
            )
            return
        requested = min(snapshot.free_slots, snapshot.eligible_count, self.max_targets.value())
        answer = QMessageBox.question(
            self,
            "Подтверждение волны",
            f"Запустить одну волну?\n\nЦелей максимум: {requested}\n"
            f"Мегатранспортировщиков на цель: {self.ship_count.value()}\n"
            f"Свободных slots: {snapshot.free_slots}\n\n"
            "V2 остановится на первой ошибке или неоднозначной отправке и не будет повторять её автоматически.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        try:
            result = self.context.run_farm_wave(
                ship_count=self.ship_count.value(),
                max_targets=self.max_targets.value(),
            )
        except Exception as exc:
            self.result_label.setText(f"Волна не запущена: {exc}")
        else:
            targets = ", ".join(result.verified_targets) or "—"
            self.result_label.setText(
                f"Волна: requested {result.requested}, attempted {result.attempted}, "
                f"verified {result.verified} · {targets}. {result.stopped_reason}"
            )
        finally:
            self._set_busy(False)
        self.check_ready()

    def _render(self, snapshot: FarmSnapshot) -> None:
        self._snapshot = snapshot
        self.state_value.setText(snapshot.state.value)
        self.detail_value.setText(snapshot.detail)
        self.metrics_value.setText(
            f"Цели {snapshot.eligible_count} · slots {snapshot.free_slots} · "
            f"blocking {snapshot.blocking_attacks} · unresolved {snapshot.unresolved_actions}"
        )
        self.wave_button.setEnabled(snapshot.state is FarmState.READY)

    def _set_busy(self, busy: bool) -> None:
        self.check_button.setEnabled(not busy)
        self.wave_button.setEnabled((not busy) and self._snapshot is not None and self._snapshot.state is FarmState.READY)
        self.ship_count.setEnabled(not busy)
        self.max_targets.setEnabled(not busy)
