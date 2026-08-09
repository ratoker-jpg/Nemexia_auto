from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel

from v2.application.discovery_scan import DISCOVERY_SEQUENCE
from v2.ui.components import SectionCard, StateBanner, command_button
from v2.ui.pages.asteroids import AsteroidsPage as ManualAsteroidsPage
from v2.ui.theme import SPACING


class AsteroidsPage(ManualAsteroidsPage):
    """AUTO-11 operator surface layered over the existing bounded manual asteroid page.

    This class is presentation-only. It reads/writes autorenew state exclusively via
    typed application-context methods and never owns browser, scheduler, persistence,
    selector or SendFleet behavior.
    """

    _BLOCKED_STATUSES = frozenset({"blocked"})
    _AMBIGUOUS_STATUSES = frozenset({"stopped_ambiguous"})

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)

        card = SectionCard(
            "Asteroid autorenew",
            "AUTO-11 · explicit Start/Stop · verified 3×40 discovery · persistent safety state.",
            object_name="AutorenewCard",
            parent=self,
        )
        card.setObjectName("AsteroidAutorenewCard")

        action_row = QHBoxLayout()
        action_row.setSpacing(SPACING["sm"])
        self.autorenew_start_button = command_button("Запустить autorenew", tone="primary", parent=card)
        self.autorenew_start_button.setObjectName("StartAsteroidAutorenewButton")
        self.autorenew_stop_button = command_button("Остановить autorenew", tone="danger", parent=card)
        self.autorenew_stop_button.setObjectName("StopAsteroidAutorenewButton")
        self.autorenew_stop_button.setProperty("tone", "danger")
        action_row.addWidget(self.autorenew_start_button)
        action_row.addWidget(self.autorenew_stop_button)
        action_row.addStretch(1)
        card.content_layout.addLayout(action_row)

        self.autorenew_banner = StateBanner(
            "STOPPED",
            "Autorenew запускается только явной кнопкой Start и после рестарта остаётся disarmed.",
            tone="info",
            parent=card,
        )
        self.autorenew_banner.setObjectName("AsteroidAutorenewState")
        card.content_layout.addWidget(self.autorenew_banner)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(SPACING["lg"])
        metrics.setVerticalSpacing(SPACING["xs"])
        labels = (
            ("PROGRESS", "AutorenewProgress"),
            ("CURRENT G:S", "AutorenewCurrentSystem"),
            ("NEXT CYCLE", "AutorenewNextCycle"),
            ("LAST VERIFIED RETURN", "AutorenewLastReturn"),
            ("LAST RESULT / ERROR", "AutorenewLastResult"),
        )
        self._autorenew_values: dict[str, QLabel] = {}
        for column, (title, object_name) in enumerate(labels[:4]):
            heading = QLabel(title, card)
            heading.setObjectName("MetricLabel")
            value = QLabel("—", card)
            value.setObjectName(object_name)
            metrics.addWidget(heading, 0, column)
            metrics.addWidget(value, 1, column)
            self._autorenew_values[object_name] = value

        result_heading = QLabel(labels[4][0], card)
        result_heading.setObjectName("MetricLabel")
        self.autorenew_result_value = QLabel("—", card)
        self.autorenew_result_value.setObjectName(labels[4][1])
        self.autorenew_result_value.setWordWrap(True)
        metrics.addWidget(result_heading, 2, 0, 1, 4)
        metrics.addWidget(self.autorenew_result_value, 3, 0, 1, 4)
        metrics.setColumnStretch(4, 1)
        card.content_layout.addLayout(metrics)

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, card)

        self.autorenew_start_button.clicked.connect(self._start_autorenew)
        self.autorenew_stop_button.clicked.connect(self._stop_autorenew)

        self._autorenew_last_error = ""
        self._autorenew_ui_timer_id = self.startTimer(1000)
        self._refresh_autorenew_status()

    @staticmethod
    def _display_time(raw: str | None) -> str:
        if not raw:
            return "—"
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
            return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            return str(raw)

    @classmethod
    def _presentation_state(cls, state) -> tuple[str, str]:
        if state is None:
            return "BLOCKED", "warning"
        status = str(state.status)
        if status in cls._AMBIGUOUS_STATUSES:
            return "AMBIGUOUS", "danger"
        if status in cls._BLOCKED_STATUSES:
            return "BLOCKED", "warning"
        if bool(state.armed):
            return "ARMED", "success"
        return "STOPPED", "info"

    @classmethod
    def _start_allowed(cls, state) -> bool:
        if state is None or bool(state.armed):
            return False
        return str(state.status) not in (cls._BLOCKED_STATUSES | cls._AMBIGUOUS_STATUSES)

    @staticmethod
    def _current_system(scan) -> str:
        if scan is None:
            return "—"
        cursor = int(scan.cursor_index)
        if cursor <= 0:
            galaxy, solar = DISCOVERY_SEQUENCE[0]
            return f"ожидает {galaxy}:{solar}"
        galaxy, solar = DISCOVERY_SEQUENCE[min(cursor, len(DISCOVERY_SEQUENCE)) - 1]
        return f"{galaxy}:{solar}"

    def _typed_autorenew_state(self):
        reader = getattr(self.context, "asteroid_autorenew_state", None)
        if not callable(reader):
            return None
        return reader()

    def _typed_discovery_scan(self, scan_id: str | None):
        if not scan_id:
            return None
        reader = getattr(self.context, "discovery_scan", None)
        if not callable(reader):
            return None
        return reader(str(scan_id))

    def _manual_controls(self):
        return (
            self.read_button,
            self.prepare_button,
            self.send_button,
            self.source_coord,
            self.recycler_count,
            self.safety_seconds,
            self.table,
        )

    def _sync_control_interlock(self, state, *, state_unknown: bool) -> None:
        autorenew_armed = bool(state is not None and state.armed)
        manual_locked = state_unknown or autorenew_armed
        if not self._series_running:
            for widget in self._manual_controls():
                widget.setEnabled(not manual_locked)
        self.stop_button.setEnabled(bool(self._series_running))

        self.autorenew_start_button.setEnabled(
            not state_unknown
            and not self._series_running
            and self._start_allowed(state)
        )
        # A failed typed Stop may leave the authoritative scheduler armed. Keep
        # Stop available whenever the latest successfully-read state proves that.
        self.autorenew_stop_button.setEnabled(
            not state_unknown and autorenew_armed
        )

    def _refresh_autorenew_status(self) -> None:
        state = None
        scan = None
        state_error = ""
        scan_error = ""

        try:
            state = self._typed_autorenew_state()
        except Exception as exc:
            state_error = str(exc) or exc.__class__.__name__
            self._autorenew_last_error = state_error
        else:
            try:
                scan = self._typed_discovery_scan(None if state is None else state.active_scan_id)
            except Exception as exc:
                scan_error = str(exc) or exc.__class__.__name__

        if scan_error:
            self._autorenew_values["AutorenewProgress"].setText("—/120")
            self._autorenew_values["AutorenewCurrentSystem"].setText("—")
        else:
            if scan is not None:
                progress = int(scan.cursor_index)
            elif state is not None and str(state.status) == "waiting_return":
                progress = len(DISCOVERY_SEQUENCE)
            else:
                progress = 0
            self._autorenew_values["AutorenewProgress"].setText(f"{progress}/120")
            self._autorenew_values["AutorenewCurrentSystem"].setText(self._current_system(scan))

        self._autorenew_values["AutorenewNextCycle"].setText(
            self._display_time(None if state is None else state.next_cycle_at)
        )
        self._autorenew_values["AutorenewLastReturn"].setText(
            self._display_time(None if state is None else state.last_return_at)
        )

        if state_error:
            self.autorenew_banner.set_state(
                "ERROR",
                "Typed autorenew state недоступен; manual/auto controls fail closed до подтверждённого state read.",
                "danger",
            )
            self._sync_control_interlock(state, state_unknown=True)
            self.autorenew_result_value.setText(self._autorenew_last_error)
            return

        # A discovery progress read is ancillary. Never discard a successfully
        # read authoritative scheduler state, especially an armed state with Stop.
        self._sync_control_interlock(state, state_unknown=False)
        if scan_error:
            self.autorenew_banner.set_state(
                "ERROR",
                f"Autorenew state подтверждён ({state.status if state is not None else 'unavailable'}); progress 3×40 недоступен.",
                "danger",
            )
            self.autorenew_result_value.setText(f"Discovery progress unavailable: {scan_error}")
            return

        title, tone = self._presentation_state(state)
        if state is None:
            self.autorenew_banner.set_state(
                title,
                "AUTO-11 typed context недоступен в этом runtime.",
                tone,
            )
            detail = "Typed autorenew service unavailable"
        elif self._autorenew_last_error:
            # Preserve the latest operator-visible failure, but reconcile controls
            # against the fresh authoritative typed state so Stop is never locked out.
            self.autorenew_banner.set_state(
                "ERROR",
                f"Последняя операция завершилась ошибкой; authoritative state: {state.status}.",
                "danger",
            )
            detail = self._autorenew_last_error
        else:
            self.autorenew_banner.set_state(
                title,
                f"{state.status} · session={state.session_id or '—'} · source={state.source_coord or '—'}",
                tone,
            )
            detail = state.detail or "—"
        self.autorenew_result_value.setText(detail)

    def _start_autorenew(self) -> None:
        if self._series_running:
            return
        start = getattr(self.context, "start_asteroid_autorenew", None)
        if not callable(start):
            self._autorenew_last_error = "V2 asteroid autorenew typed Start service is unavailable"
            self._refresh_autorenew_status()
            return
        source = self.source_coord.text().strip()
        try:
            buffer_minutes = int(self.context.v2_setting("farm_return_buffer_minutes", 5))
            start(
                source=source,
                recycler_count=int(self.recycler_count.value()),
                max_flights=15,
                safety_seconds=int(self.safety_seconds.value()),
                buffer_minutes=max(0, buffer_minutes),
                start_immediately=True,
            )
        except Exception as exc:
            self._autorenew_last_error = str(exc) or exc.__class__.__name__
            self._refresh_autorenew_status()
            return
        self._autorenew_last_error = ""
        self._refresh_autorenew_status()

    def _stop_autorenew(self) -> None:
        stop = getattr(self.context, "stop_asteroid_autorenew", None)
        if not callable(stop):
            self._autorenew_last_error = "V2 asteroid autorenew typed Stop service is unavailable"
            self._refresh_autorenew_status()
            return
        try:
            stop(detail="Stopped by operator from Asteroids UI")
        except Exception as exc:
            self._autorenew_last_error = str(exc) or exc.__class__.__name__
            self._refresh_autorenew_status()
            return
        self._autorenew_last_error = ""
        self._refresh_autorenew_status()

    def _set_series_controls(self, running: bool) -> None:
        super()._set_series_controls(running)
        if hasattr(self, "autorenew_start_button"):
            self._refresh_autorenew_status()

    def reload_view(self) -> None:
        super().reload_view()
        if hasattr(self, "autorenew_banner"):
            self._refresh_autorenew_status()

    def timerEvent(self, event) -> None:
        if event.timerId() == getattr(self, "_autorenew_ui_timer_id", -1):
            self._refresh_autorenew_status()
            return
        super().timerEvent(event)
