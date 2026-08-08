from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
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


SCHEDULER_INTERVAL_MS = 30_000


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class FarmPage(QWidget):
    """Typed AutoFarm page with an explicit, non-persistent in-session scheduler."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._snapshot: FarmSnapshot | None = None
        self._armed = False
        self._busy = False
        self._cooldown_until: datetime | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(SCHEDULER_INTERVAL_MS)
        self._timer.timeout.connect(self._scheduler_tick)

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
        self.scheduler_value = QLabel("Цикл: выключен", status_card)
        self.scheduler_value.setObjectName("Muted")
        grid.addWidget(QLabel("State", status_card), 1, 0)
        grid.addWidget(self.state_value, 1, 1)
        grid.addWidget(self.detail_value, 2, 0, 1, 2)
        grid.addWidget(self.metrics_value, 3, 0, 1, 2)
        grid.addWidget(self.scheduler_value, 4, 0, 1, 2)
        layout.addWidget(status_card)

        controls = QFrame(self)
        controls.setObjectName("InfoCard")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 16)
        controls_layout.setSpacing(10)
        controls_title = QLabel("Параметры волны", controls)
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
        controls_layout.addLayout(row)

        cycle_row = QHBoxLayout()
        self.start_button = QPushButton("Запустить цикл", controls)
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_cycle)
        cycle_row.addWidget(self.start_button)
        self.stop_button = QPushButton("Остановить цикл", controls)
        self.stop_button.setObjectName("SecondaryButton")
        self.stop_button.clicked.connect(lambda: self._disarm("остановлен вручную"))
        self.stop_button.setEnabled(False)
        cycle_row.addWidget(self.stop_button)
        cycle_row.addStretch(1)
        controls_layout.addLayout(cycle_row)

        note = QLabel(
            "Цикл живёт только в текущем запуске app_qt.py и после перезапуска всегда выключен. "
            "Каждые 30 секунд он заново читает live flights/capacity и отправляет волну только в state=ready. "
            "Return-buffer удерживается в памяти текущего цикла. Pending/ambiguous, live error или ошибка волны разоружают цикл. "
            "Автоматической разведки и пополнения очереди в этом PR ещё нет.",
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

    def _refresh_snapshot(self) -> FarmSnapshot:
        status = self.context.refresh_live_source()
        if status.available:
            self.context.reconcile_raid_actions()
        snapshot = self.context.farm_snapshot()
        self._remember_ready_at(snapshot.ready_at)
        self._render(snapshot)
        return snapshot

    def check_ready(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        try:
            self._refresh_snapshot()
        except Exception as exc:
            self.result_label.setText(f"Проверка остановлена: {exc}")
        finally:
            self._set_busy(False)

    def run_wave(self) -> None:
        if self._armed:
            QMessageBox.information(self, "Автофарм V2", "Сначала останови непрерывный цикл.")
            return
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
        self._execute_wave()
        self.check_ready()

    def start_cycle(self) -> None:
        if self._armed or self._busy:
            return
        self.check_ready()
        snapshot = self._snapshot
        if snapshot is None:
            return
        forbidden = {
            FarmState.ACTIONS_DISABLED,
            FarmState.LIVE_NOT_CHECKED,
            FarmState.LIVE_UNAVAILABLE,
            FarmState.BLOCKED_UNRESOLVED,
            FarmState.NO_TARGETS,
        }
        if snapshot.state in forbidden:
            QMessageBox.warning(self, "Автофарм V2", snapshot.detail)
            return
        answer = QMessageBox.question(
            self,
            "Запуск непрерывного цикла",
            "Запустить автофарм до ручной остановки или safety-stop?\n\n"
            f"Кораблей на цель: {self.ship_count.value()}\n"
            f"Макс. целей за волну: {self.max_targets.value()}\n"
            "Проверка состояния: каждые 30 секунд.\n\n"
            "Цикл НЕ включается автоматически после перезапуска. "
            "Любая ambiguous отправка, unresolved journal или live failure остановит цикл.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._armed = True
        self._timer.start()
        self.scheduler_value.setText("Цикл: вооружён · проверка каждые 30 сек")
        self._sync_buttons()
        self._scheduler_tick()

    def _scheduler_tick(self) -> None:
        if not self._armed or self._busy:
            return
        self._set_busy(True)
        try:
            snapshot = self._refresh_snapshot()
            hard_stop = {
                FarmState.ACTIONS_DISABLED,
                FarmState.LIVE_UNAVAILABLE,
                FarmState.BLOCKED_UNRESOLVED,
                FarmState.NO_TARGETS,
            }
            if snapshot.state in hard_stop:
                self._disarm(f"safety-stop: {snapshot.detail}")
                return
            if snapshot.state in {FarmState.WAITING_RETURN, FarmState.WAITING_CAPACITY}:
                self.scheduler_value.setText(f"Цикл: ожидание · {snapshot.state.value}")
                return
            if snapshot.state is not FarmState.READY:
                return

            now = datetime.now(timezone.utc)
            if self._cooldown_until is not None and now < self._cooldown_until:
                self.scheduler_value.setText(
                    f"Цикл: return-buffer до {self._cooldown_until.replace(microsecond=0).isoformat()}"
                )
                return

            result = self.context.run_farm_wave(
                ship_count=self.ship_count.value(),
                max_targets=self.max_targets.value(),
            )
            targets = ", ".join(result.verified_targets) or "—"
            self.result_label.setText(
                f"Автоволна: requested {result.requested}, attempted {result.attempted}, "
                f"verified {result.verified} · {targets}. {result.stopped_reason}"
            )
            if result.stopped_reason != "wave complete" or result.verified < result.attempted:
                self._disarm(f"safety-stop: {result.stopped_reason}")
                return

            post = self._refresh_snapshot()
            if post.state in {FarmState.BLOCKED_UNRESOLVED, FarmState.LIVE_UNAVAILABLE}:
                self._disarm(f"safety-stop: {post.detail}")
                return
            self.scheduler_value.setText("Цикл: волна подтверждена · ждём возвраты")
        except Exception as exc:
            self._disarm(f"safety-stop: {exc}")
        finally:
            self._set_busy(False)

    def _execute_wave(self) -> None:
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

    def _remember_ready_at(self, value: str | None) -> None:
        parsed = _parse_dt(value)
        if parsed is not None and (self._cooldown_until is None or parsed > self._cooldown_until):
            self._cooldown_until = parsed

    def _disarm(self, reason: str) -> None:
        self._armed = False
        self._timer.stop()
        self.scheduler_value.setText(f"Цикл: выключен · {reason}")
        self._sync_buttons()

    def _render(self, snapshot: FarmSnapshot) -> None:
        self._snapshot = snapshot
        self.state_value.setText(snapshot.state.value)
        self.detail_value.setText(snapshot.detail)
        ready = f" · ready_at {snapshot.ready_at}" if snapshot.ready_at else ""
        self.metrics_value.setText(
            f"Цели {snapshot.eligible_count} · slots {snapshot.free_slots} · "
            f"blocking {snapshot.blocking_attacks} · unresolved {snapshot.unresolved_actions}{ready}"
        )
        self._sync_buttons()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        ready = self._snapshot is not None and self._snapshot.state is FarmState.READY
        self.check_button.setEnabled(not self._busy)
        self.wave_button.setEnabled((not self._busy) and (not self._armed) and ready)
        self.start_button.setEnabled((not self._busy) and (not self._armed))
        self.stop_button.setEnabled(self._armed)
        self.ship_count.setEnabled((not self._busy) and (not self._armed))
        self.max_targets.setEnabled((not self._busy) and (not self._armed))
