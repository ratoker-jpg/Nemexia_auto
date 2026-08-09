from __future__ import annotations

from typing import Any


class QtAsteroidAutorenewDriver:
    """Thin Qt event-loop driver for the typed AUTO-11 application API.

    PySide6 is imported lazily so non-Qt Python CI can import the infrastructure
    package without requiring the GUI wheel. The driver contains no browser
    selectors, CDP calls, business decisions or SendFleet logic.
    """

    def __init__(self, context: Any, *, interval_ms: int = 1000, parent=None) -> None:
        from PySide6.QtCore import QTimer

        self.context = context
        self.timer = QTimer(parent)
        self.timer.setInterval(max(250, int(interval_ms)))
        self.timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _tick(self) -> None:
        state_reader = getattr(self.context, "asteroid_autorenew_state", None)
        tick = getattr(self.context, "tick_asteroid_autorenew", None)
        if not callable(state_reader) or not callable(tick):
            return
        try:
            state = state_reader()
            if state is None or not bool(state.armed):
                return
            tick()
        except Exception as exc:
            # A scheduler error must never turn into a blind retry on the next Qt
            # timeout. Disarm future ticks through the typed application boundary.
            stopper = getattr(self.context, "stop_asteroid_autorenew", None)
            if callable(stopper):
                try:
                    stopper(detail=f"Qt autorenew driver stopped after error: {exc}")
                except Exception:
                    pass
