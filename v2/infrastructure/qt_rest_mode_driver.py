from __future__ import annotations

from typing import Any, Callable


class QtRestModeDriver:
    """Thin event-loop pump for the typed AUTO-12 API; never arms Rest Mode."""

    def __init__(
        self,
        context: Any,
        *,
        interval_ms: int = 1000,
        parent=None,
        notify: Callable[[str, str], None] | None = None,
    ) -> None:
        from PySide6.QtCore import QTimer

        self.context = context
        self.parent = parent
        self.notify = notify or self._qt_notify
        self.timer = QTimer(parent)
        self.timer.setInterval(max(250, int(interval_ms)))
        self.timer.timeout.connect(self._tick)
        self._last_notice_key = ""

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _qt_notify(self, title: str, message: str) -> None:
        """Best-effort local signal; notification failure never changes safety state."""

        try:
            from PySide6.QtWidgets import QApplication, QSystemTrayIcon

            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
            tray = getattr(self, "_tray", None)
            if tray is None:
                tray = QSystemTrayIcon(self.parent)
                app = QApplication.instance()
                if app is not None:
                    tray.setIcon(app.windowIcon())
                tray.show()
                self._tray = tray
            tray.showMessage(str(title), str(message), QSystemTrayIcon.MessageIcon.Warning, 10000)
        except Exception:
            return

    def _notify_once(self, key: str, title: str, message: str) -> None:
        if key == self._last_notice_key:
            return
        self._last_notice_key = key
        try:
            self.notify(str(title), str(message))
        except Exception:
            pass

    def _tick(self) -> None:
        state_reader = getattr(self.context, "rest_mode_state", None)
        tick = getattr(self.context, "tick_rest_mode", None)
        if not callable(state_reader) or not callable(tick):
            return
        try:
            before = state_reader()
            if before is None or not bool(before.armed):
                return
            result = tick()
            state = result.state
            if bool(getattr(result, "warning_emitted", False)):
                self._notify_once(
                    f"activity:{state.activity_epoch}",
                    "Nemexia · проверка активности",
                    f"До автоматической проверки активности осталось {state.last_activity_minutes} мин.",
                )
            if not state.armed and state.status in {
                "CAPTCHA_REQUIRED",
                "BLOCKED_BROWSER",
                "BLOCKED_IDENTITY",
                "BLOCKED_AMBIGUOUS",
                "ERROR",
            }:
                self._notify_once(
                    f"stop:{state.status}:{state.updated_at}",
                    "Nemexia · Rest Mode остановлен",
                    state.detail or state.last_error or state.status,
                )
        except Exception as exc:
            # Never turn a local driver failure into an automatic browser retry.
            stopper = getattr(self.context, "stop_rest_mode", None)
            if callable(stopper):
                try:
                    stopper(detail=f"Qt Rest Mode driver stopped after error: {exc}")
                except Exception:
                    pass
            self._notify_once(
                f"driver:{exc.__class__.__name__}:{exc}",
                "Nemexia · Rest Mode ошибка",
                str(exc) or exc.__class__.__name__,
            )
