from __future__ import annotations

from typing import Any, Callable


_TERMINAL_NOTICE_STATUSES = frozenset(
    {
        "CAPTCHA_REQUIRED",
        "BLOCKED_BROWSER",
        "BLOCKED_IDENTITY",
        "BLOCKED_BUSY",
        "BLOCKED_AMBIGUOUS",
        "ERROR",
    }
)


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
        # Keep channels separate: a CAPTCHA/BLOCKED notification must not erase the
        # activity-warning dedupe identity for a later same-epoch explicit restart.
        self._last_activity_notice_key = ""
        self._last_terminal_notice_key = ""
        self._last_driver_notice_key = ""

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

    def _notify_once(self, channel: str, key: str, title: str, message: str) -> None:
        attr = {
            "activity": "_last_activity_notice_key",
            "terminal": "_last_terminal_notice_key",
            "driver": "_last_driver_notice_key",
        }[str(channel)]
        if key == getattr(self, attr, ""):
            return
        setattr(self, attr, key)
        try:
            self.notify(str(title), str(message))
        except Exception:
            pass

    @staticmethod
    def _identity_notice_key(state: Any) -> str:
        return ":".join(
            str(getattr(state, field, "") or "")
            for field in (
                "server_host",
                "account_fingerprint",
                "planet_id",
                "planet_coord",
            )
        )

    def _notify_state(self, state: Any) -> None:
        """Surface persisted Start/tick outcomes even when this driver did not create them."""

        if state is None:
            return
        status = str(getattr(state, "status", "") or "")
        identity_key = self._identity_notice_key(state)

        # Explicit Start can synchronously persist ACTIVITY_WARNING with the warning
        # already deduped in SQLite. Poll the typed state itself so that first-low
        # starts still notify even though the next tick has warning_emitted=False.
        if (
            status == "ACTIVITY_WARNING"
            and bool(getattr(state, "activity_warning_sent", False))
            and getattr(state, "last_activity_minutes", None) is not None
        ):
            self._notify_once(
                "activity",
                f"activity:{identity_key}:{int(getattr(state, 'activity_epoch', 0))}",
                "Nemexia · проверка активности",
                f"До автоматической проверки активности осталось "
                f"{int(state.last_activity_minutes)} мин.",
            )

        # Explicit Start may also fail before the first armed timer tick. Terminal
        # state polling makes CAPTCHA/BLOCKED/ERROR notification independent from
        # which UI surface initiated Start.
        if not bool(getattr(state, "armed", False)) and status in _TERMINAL_NOTICE_STATUSES:
            self._notify_once(
                "terminal",
                f"terminal:{identity_key}:{status}:{getattr(state, 'updated_at', '')}",
                "Nemexia · Rest Mode остановлен",
                str(
                    getattr(state, "detail", "")
                    or getattr(state, "last_error", "")
                    or status
                ),
            )

    def _tick(self) -> None:
        state_reader = getattr(self.context, "rest_mode_state", None)
        tick = getattr(self.context, "tick_rest_mode", None)
        if not callable(state_reader) or not callable(tick):
            return
        try:
            before = state_reader()
            # Observe persisted Start outcomes before deciding whether a scheduler
            # tick is due. This covers immediate CAPTCHA/BLOCKED and <=25 results.
            self._notify_state(before)
            if before is None or not bool(before.armed):
                return
            result = tick()
            self._notify_state(result.state)
        except Exception as exc:
            # Never turn a local driver failure into an automatic browser retry.
            stopper = getattr(self.context, "stop_rest_mode", None)
            if callable(stopper):
                try:
                    stopper(detail=f"Qt Rest Mode driver stopped after error: {exc}")
                except Exception:
                    pass
            self._notify_once(
                "driver",
                f"driver:{exc.__class__.__name__}:{exc}",
                "Nemexia · Rest Mode ошибка",
                str(exc) or exc.__class__.__name__,
            )
