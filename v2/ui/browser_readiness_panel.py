from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from v2.ui.components import StatusPill
from v2.ui.theme import SPACING


_READY_TEXT = {
    "browser": "connected",
    "account": "identified",
    "planet": "selected",
    "fleets": "ready",
    "messages": "ready",
    "galaxy": "ready",
}


class _ReadinessSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _ReadinessTask(QRunnable):
    def __init__(self, provider: Callable[[], object]) -> None:
        super().__init__()
        self.provider = provider
        self.signals = _ReadinessSignals()

    @Slot()
    def run(self) -> None:
        try:
            snapshot = self.provider()
        except Exception as exc:  # UI boundary: surface service errors, never crash Qt.
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.signals.completed.emit(snapshot)


class BrowserReadinessPanel(QFrame):
    """UI-only projection of the application Browser Readiness contract."""

    def __init__(
        self,
        context: object,
        parent: QWidget | None = None,
        *,
        refresh_interval_ms: int = 15_000,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.setObjectName("BrowserReadinessBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xs"], SPACING["xl"], SPACING["xs"])
        layout.setSpacing(SPACING["sm"])

        self._pills: dict[str, StatusPill] = {}
        for key, label in (
            ("browser", "Browser"),
            ("account", "Account"),
            ("planet", "Planet"),
            ("fleets", "Fleets"),
            ("messages", "Messages"),
            ("galaxy", "Galaxy"),
        ):
            pill = StatusPill(f"{label} · …", "neutral", self)
            pill.setProperty("readinessKey", key)
            pill.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._pills[key] = pill
            layout.addWidget(pill)

        layout.addStretch(1)
        self.refresh_button = QPushButton("Обновить", self)
        self.refresh_button.setProperty("compact", "true")
        self.refresh_button.setToolTip("Обновить состояние браузера, аккаунта, планеты и игровых страниц")
        self.refresh_button.clicked.connect(self.refresh_async)
        layout.addWidget(self.refresh_button)

        self._pool = QThreadPool.globalInstance()
        self._task: _ReadinessTask | None = None
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(max(5_000, int(refresh_interval_ms)))
        self._timer.timeout.connect(self.refresh_async)
        self._timer.start()
        QTimer.singleShot(0, self.refresh_async)

    def _set_pill(self, key: str, text: str, tone: str, detail: str = "") -> None:
        pill = self._pills[key]
        label = pill.text().split(" · ", 1)[0]
        pill.setText(f"{label} · {text}")
        pill.setProperty("tone", tone)
        pill.setToolTip(detail)
        pill.style().unpolish(pill)
        pill.style().polish(pill)

    def _set_all(self, text: str, tone: str, detail: str) -> None:
        for key in self._pills:
            self._set_pill(key, text, tone, detail)

    @staticmethod
    def _state_value(item: object) -> str:
        state = getattr(item, "state", "not_ready")
        return str(getattr(state, "value", state)).casefold()

    @staticmethod
    def _render_state(key: str, state: str) -> tuple[str, str]:
        if state == "ready":
            return f"● {_READY_TEXT.get(key, 'ready')}", "success"
        if state == "stopped":
            return "■ stopped", "danger"
        if state == "blocked":
            return "× blocked", "danger"
        return "○ not ready", "warning"

    @Slot(object)
    def _apply_snapshot(self, snapshot: object) -> None:
        self._busy = False
        self.refresh_button.setEnabled(True)
        self._task = None
        if snapshot is None:
            self._set_all("× unavailable", "warning", "Browser Readiness недоступен")
            return
        for key in self._pills:
            item = getattr(snapshot, key, None)
            if item is None:
                self._set_pill(key, "× unavailable", "warning", "Компонент readiness недоступен")
                continue
            state = self._state_value(item)
            text, tone = self._render_state(key, state)
            self._set_pill(key, text, tone, str(getattr(item, "detail", "") or ""))

    @Slot(str)
    def _apply_error(self, detail: str) -> None:
        self._busy = False
        self.refresh_button.setEnabled(True)
        self._task = None
        tone = "danger" if "captcha" in detail.casefold() else "warning"
        text = "■ stopped" if tone == "danger" else "× unavailable"
        self._set_all(text, tone, detail)

    @Slot()
    def refresh_async(self) -> None:
        if self._busy:
            return
        provider = getattr(self.context, "browser_readiness", None)
        if not callable(provider):
            self._set_all("× unavailable", "warning", "Browser Readiness service недоступен")
            return
        self._busy = True
        self.refresh_button.setEnabled(False)
        task = _ReadinessTask(provider)
        task.signals.completed.connect(self._apply_snapshot)
        task.signals.failed.connect(self._apply_error)
        self._task = task
        self._pool.start(task)
