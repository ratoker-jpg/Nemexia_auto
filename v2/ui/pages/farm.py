from __future__ import annotations

import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QWidget

from v2.application.context import V2ApplicationContext
from v2.application.farm_controller import FarmSnapshot, FarmState
from v2.application.recon_refill import ReconRefillState
from v2.ui.components import SectionCard, StateBanner, StatusPill, command_button, page_layout
from v2.ui.theme import SPACING


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

        layout = page_layout(self)

        hero = SectionCard(
            "AutoFarm command",
            "Главный операционный экран V2. Цикл всегда стартует разоружённым и требует явного запуска в текущей сессии.",
            object_name="CommandCard",
            parent=self,
        )
        hero_row = QHBoxLayout()
        hero_row.setSpacing(SPACING["md"])
        state_label = QLabel("STATE", hero)
        state_label.setObjectName("MetricLabel")
        hero_row.addWidget(state_label)
        self.state_value = StatusPill("Не проверено", "neutral", hero)
        hero_row.addWidget(self.state_value)
        hero_row.addStretch(1)
        self.scheduler_value = QLabel("Цикл: выключен", hero)
        self.scheduler_value.setObjectName("BodyStrong")
        hero_row.addWidget(self.scheduler_value)
        hero.content_layout.addLayout(hero_row)

        self.detail_value = QLabel("Нажми «Проверить готовность».", hero)
        self.detail_value.setObjectName("Muted")
        self.detail_value.setWordWrap(True)
        hero.content_layout.addWidget(self.detail_value)
        self.metrics_value = QLabel("Цели — · slots — · blocking — · unresolved —", hero)
        self.metrics_value.setObjectName("Mono")
        self.metrics_value.setWordWrap(True)
        hero.content_layout.addWidget(self.metrics_value)
        layout.addWidget(hero)

        operations = SectionCard(
            "Операции волны",
            "Проверка — read-only. Одна волна и непрерывный цикл используют уже существующий journaled dispatch и safety-stop правила.",
            object_name="CommandCard",
            parent=self,
        )
        fields = QGridLayout()
        fields.setHorizontalSpacing(SPACING["md"])
        fields.setVerticalSpacing(SPACING["xs"])
        ship_label = QLabel("МЕГАТРАНСПОРТИРОВЩИКИ / ЦЕЛЬ", operations)
        ship_label.setObjectName("MetricLabel")
        target_label = QLabel("МАКС. ЦЕЛЕЙ / ВОЛНУ", operations)
        target_label.setObjectName("MetricLabel")
        fields.addWidget(ship_label, 0, 0)
        fields.addWidget(target_label, 0, 1)
        self.ship_count = QSpinBox(operations)
        self.ship_count.setRange(1, 100000)
        self.ship_count.setValue(25)
        self.max_targets = QSpinBox(operations)
        self.max_targets.setRange(1, 1000)
        self.max_targets.setValue(15)
        fields.addWidget(self.ship_count, 1, 0)
        fields.addWidget(self.max_targets, 1, 1)
        fields.setColumnStretch(2, 1)
        operations.content_layout.addLayout(fields)

        action_row = QHBoxLayout()
        action_row.setSpacing(SPACING["sm"])
        self.check_button = command_button("Проверить готовность", tone="secondary", parent=operations)
        self.check_button.setObjectName("SecondaryButton")
        self.check_button.clicked.connect(self.check_ready)
        action_row.addWidget(self.check_button)
        self.wave_button = command_button("Выполнить одну волну", tone="warning", parent=operations)
        self.wave_button.setObjectName("PrimaryButton")
        self.wave_button.setProperty("tone", "warning")
        self.wave_button.clicked.connect(self.run_wave)
        action_row.addWidget(self.wave_button)
        action_row.addStretch(1)
        operations.content_layout.addLayout(action_row)
        layout.addWidget(operations)

        recovery = SectionCard(
            "Recon recovery · текущая сессия",
            "Exact Spy fleet ID существующей строки fleets.php. Поле не сохраняется и не создаёт новый espionage route.",
            parent=self,
        )
        recon_row = QHBoxLayout()
        recon_row.setSpacing(SPACING["sm"])
        self.spy_fleet_id = QLineEdit(recovery)
        self.spy_fleet_id.setObjectName("FarmSpyFleetId")
        self.spy_fleet_id.setPlaceholderText("Exact fleet ID, например 152272")
        self.spy_fleet_id.setMaximumWidth(280)
        recon_row.addWidget(self.spy_fleet_id)
        recon_row.addStretch(1)
        recovery.content_layout.addLayout(recon_row)
        layout.addWidget(recovery)

        cycle = SectionCard(
            "Непрерывный цикл",
            "Arm существует только в памяти текущего app_qt.py. Stop предотвращает следующий шаг; ambiguous/CAPTCHA/live failure разоружают цикл.",
            object_name="CommandCard",
            parent=self,
        )
        cycle_row = QHBoxLayout()
        cycle_row.setSpacing(SPACING["sm"])
        self.start_button = command_button("Запустить цикл", tone="warning", parent=cycle)
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setProperty("tone", "warning")
        self.start_button.clicked.connect(self.start_cycle)
        cycle_row.addWidget(self.start_button)
        self.stop_button = command_button("Остановить цикл", tone="danger", parent=cycle)
        self.stop_button.setObjectName("SecondaryButton")
        self.stop_button.setProperty("tone", "danger")
        self.stop_button.clicked.connect(lambda: self._disarm("остановлен вручную"))
        self.stop_button.setEnabled(False)
        cycle_row.addWidget(self.stop_button)
        cycle_row.addStretch(1)
        cycle.content_layout.addLayout(cycle_row)

        safety = StateBanner(
            "Safety contract",
            "Цикл живёт только в текущем запуске app_qt.py и после перезапуска всегда выключен. "
            "Spy fleet ID тоже не сохраняется: пользователь задаёт exact ID существующей строки fleets.php для текущей сессии. "
            "Каждые 30 секунд цикл перечитывает live state. При исчерпании очереди он может выполнить только один journaled "
            "processSpy по этому exact ID, принять exact fresh report и сделать deterministic AutoFarm refill. "
            "Fresh scan без eligible целей включает отдельный persisted cooldown 25 минут. CAPTCHA, stale/no fresh evidence, "
            "pending/ambiguous raid/spy journal, live error или неоднозначный side effect разоружают цикл без автоматического повтора.",
            tone="warning",
            parent=cycle,
        )
        cycle.content_layout.addWidget(safety)
        self.result_label = QLabel("", cycle)
        self.result_label.setObjectName("Muted")
        self.result_label.setWordWrap(True)
        cycle.content_layout.addWidget(self.result_label)
        layout.addWidget(cycle)
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
        }
        if snapshot.state in forbidden:
            QMessageBox.warning(self, "Автофарм V2", snapshot.detail)
            return

        fleet_id = self.spy_fleet_id.text().strip()
        if not fleet_id:
            QMessageBox.warning(
                self,
                "Автофарм V2",
                "Для непрерывного recovery укажи exact Spy fleet ID существующей строки fleets.php. ID не сохраняется.",
            )
            return
        prepare = getattr(self.context, "prepare_spy", None)
        if not callable(prepare):
            QMessageBox.critical(self, "Автофарм V2", "V2 spy action service недоступен.")
            return
        try:
            spy = prepare(fleet_id)
        except Exception as exc:
            QMessageBox.warning(self, "Автофарм V2", f"Spy fleet не готов: {exc}")
            return

        answer = QMessageBox.question(
            self,
            "Запуск непрерывного цикла",
            "Запустить автофарм до ручной остановки или safety-stop?\n\n"
            f"Кораблей на цель: {self.ship_count.value()}\n"
            f"Макс. целей за волну: {self.max_targets.value()}\n"
            f"Recon recovery: fleet {spy.fleet_id} · {spy.source} → {spy.target}\n"
            "Проверка состояния: каждые 30 секунд.\n\n"
            "Цикл и Spy fleet ID НЕ сохраняются после перезапуска. При need_recon будет выполнен только journaled exact-fleet "
            "processSpy; ambiguity/CAPTCHA/live failure/unresolved journal немедленно остановят цикл без повтора.",
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
            }
            if snapshot.state in hard_stop:
                self._disarm(f"safety-stop: {snapshot.detail}")
                return
            if snapshot.state is FarmState.NEED_RECON:
                self._recover_recon()
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

    def _recover_recon(self) -> None:
        fleet_id = self.spy_fleet_id.text().strip()
        if not fleet_id:
            self._disarm("safety-stop: exact Spy fleet ID отсутствует в текущей сессии")
            return
        run = getattr(self.context, "run_controlled_recon_refill", None)
        if not callable(run):
            self._disarm("safety-stop: controlled recon/refill service недоступен")
            return
        result = run(
            fleet_id,
            request_id=f"recon-cycle-{uuid.uuid4().hex}",
        )
        self.result_label.setText(result.detail)
        if result.state is ReconRefillState.REFILLED:
            self.scheduler_value.setText("Цикл: recon подтверждён · очередь пополнена · следующая волна на следующей проверке")
            self._refresh_snapshot()
            return
        if result.state in {ReconRefillState.EMPTY_COOLDOWN, ReconRefillState.COOLDOWN}:
            suffix = f" до {result.cooldown_until}" if result.cooldown_until else ""
            self.scheduler_value.setText(f"Цикл: no-target recon cooldown{suffix}")
            return
        reason = result.stop_reason.value if result.stop_reason is not None else "stopped"
        self._disarm(f"safety-stop recon · {reason}: {result.detail}")

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
        self.spy_fleet_id.setEnabled((not self._busy) and (not self._armed))
