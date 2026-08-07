from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import tkinter as tk

from farm_flight_classification_fix import _farm_attacks
from models import parse_dt, utc_now
from visual_system import FONT_CAPTION, SURFACE_2, TEXT_2


DEFAULT_RETURN_BUFFER_MINUTES = 5
MAX_RETURN_BUFFER_MINUTES = 60
_INSTALLED_CLASSES: set[type[Any]] = set()


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    return parse_dt(str(value))


def _remaining_text(deadline: datetime, now: datetime) -> str:
    seconds = max(0, int((deadline - now).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def install_farm_wave_cooldown(app_class: type[Any]) -> None:
    if app_class in _INSTALLED_CLASSES:
        return

    original_init = app_class.__init__
    original_build_queue_page = app_class._build_queue_page
    original_auto_cycle = app_class._auto_cycle
    original_send_wave = app_class._farm_send_wave
    original_set_status = app_class._set_farm_status

    def buffer_minutes(self: Any) -> int:
        var = getattr(self, "farm_return_buffer_var", None)
        try:
            value = int(var.get()) if var is not None else int(
                self.settings.get("farm_return_buffer_minutes", DEFAULT_RETURN_BUFFER_MINUTES)
            )
        except Exception:
            value = DEFAULT_RETURN_BUFFER_MINUTES
        return max(0, min(MAX_RETURN_BUFFER_MINUTES, value))

    def saved_deadline(self: Any) -> datetime | None:
        return _as_dt(self.settings.get("farm_next_cycle_at") or "")

    def save_deadline(self: Any, last_return: datetime, buffer: int | None = None) -> datetime:
        buffer = self._farm_buffer_minutes() if buffer is None else max(0, int(buffer))
        deadline = last_return + timedelta(minutes=buffer)
        values = {
            "farm_return_buffer_minutes": buffer,
            "farm_last_wave_return_at": last_return.isoformat(),
            "farm_next_cycle_at": deadline.isoformat(),
        }
        self.db.set_settings(values)
        self.settings.update(values)
        return deadline

    def clear_deadline(self: Any) -> None:
        values = {
            "farm_last_wave_return_at": "",
            "farm_next_cycle_at": "",
        }
        self.db.set_settings(values)
        self.settings.update(values)

    def save_buffer(self: Any, *_args: Any) -> None:
        buffer = self._farm_buffer_minutes()
        try:
            current = int(self.farm_return_buffer_var.get())
        except Exception:
            current = buffer
        if current != buffer:
            try:
                self.farm_return_buffer_var.set(buffer)
            except Exception:
                pass
        self.db.set_setting("farm_return_buffer_minutes", buffer)
        self.settings["farm_return_buffer_minutes"] = buffer

        # If a wave timer is currently active, changing the buffer immediately
        # recalculates that timer from the same last return instead of waiting for
        # the next wave.
        last_return = _as_dt(self.settings.get("farm_last_wave_return_at") or "")
        deadline = self._farm_saved_deadline()
        if last_return is not None and deadline is not None and deadline > utc_now():
            self._farm_save_deadline(last_return, buffer)

    def build_queue_page(self: Any) -> None:
        original_build_queue_page(self)
        if not hasattr(self, "farm_return_buffer_var"):
            initial = self.settings.get("farm_return_buffer_minutes", DEFAULT_RETURN_BUFFER_MINUTES)
            try:
                initial = max(0, min(MAX_RETURN_BUFFER_MINUTES, int(initial)))
            except Exception:
                initial = DEFAULT_RETURN_BUFFER_MINUTES
            self.farm_return_buffer_var = tk.IntVar(value=initial)
            self.settings["farm_return_buffer_minutes"] = initial
            self.db.set_setting("farm_return_buffer_minutes", initial)
            self.farm_return_buffer_var.trace_add("write", self._farm_save_buffer)

        button = getattr(self, "farm_auto_button", None)
        if button is None or getattr(self, "farm_buffer_frame", None) is not None:
            return

        frame = tk.Frame(button.master, bg=SURFACE_2)
        frame.pack(side="right", padx=(12, 0))
        self.farm_buffer_frame = frame
        tk.Label(
            frame,
            text="Буфер после возврата, мин",
            bg=SURFACE_2,
            fg=TEXT_2,
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 6))
        tk.Spinbox(
            frame,
            from_=0,
            to=MAX_RETURN_BUFFER_MINUTES,
            increment=1,
            width=4,
            textvariable=self.farm_return_buffer_var,
            justify="center",
        ).pack(side="left")

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._farm_wave_capture = False
        self._farm_wave_returns: list[datetime] = []

        # Capture return times only while the auto-farm wave is being sent. This
        # gives us the exact latest return of that wave, independent of any
        # recycling/asteroid flights occupying other slots.
        original_worker_send_raid = self.worker.send_raid

        async def capture_send_raid(*send_args: Any, **send_kwargs: Any):
            result = await original_worker_send_raid(*send_args, **send_kwargs)
            if getattr(self, "_farm_wave_capture", False):
                returned = _as_dt(result.get("return_at") if isinstance(result, dict) else None)
                if returned is not None:
                    self._farm_wave_returns.append(returned)
            return result

        self.worker.send_raid = capture_send_raid

    def set_status(self: Any, text: str, *, topbar: bool = True) -> None:
        final_text = text
        capture = bool(getattr(self, "_farm_wave_capture", False))

        if capture and text.startswith("Автофарм · отправлено"):
            returns = list(getattr(self, "_farm_wave_returns", []) or [])
            if not returns:
                try:
                    returns = [
                        flight.return_at
                        for flight in _farm_attacks(list(self.active_flights), self.home())
                        if flight.return_at is not None
                    ]
                except Exception:
                    returns = []

            latest = max(returns, default=None)
            self._farm_wave_capture = False
            if latest is not None:
                buffer = self._farm_buffer_minutes()
                deadline = self._farm_save_deadline(latest, buffer)
                final_text = (
                    f"{text} · следующий скан {deadline.astimezone().strftime('%H:%M:%S')} "
                    f"(+{buffer} мин)"
                )
                self.logger.info(
                    "Автофарм: зафиксирован таймер волны; последний возврат=%s, буфер=%s мин, следующий скан=%s",
                    latest.isoformat(),
                    buffer,
                    deadline.isoformat(),
                )
        elif capture and (
            text.startswith("Автофарм · очередь")
            or text.startswith("Автофарм · нет свободных")
            or text.startswith("Автофарм остановлен")
        ):
            self._farm_wave_capture = False
            self._farm_wave_returns = []

        original_set_status(self, final_text, topbar=topbar)

    def send_wave(self: Any) -> None:
        deadline = self._farm_saved_deadline()
        now = utc_now()
        if deadline is not None and deadline > now:
            self._set_farm_status(
                f"Автофарм · ждём таймер волны до {deadline.astimezone().strftime('%H:%M:%S')} "
                f"· осталось {_remaining_text(deadline, now)}",
                topbar=False,
            )
            return

        if not self.auto_var.get() or self.busy:
            return original_send_wave(self)

        self._farm_wave_returns = []
        self._farm_wave_capture = True
        return original_send_wave(self)

    def auto_cycle(self: Any) -> None:
        if not self.auto_var.get() or self.asteroid_auto_var.get() or self.busy:
            return original_auto_cycle(self)

        deadline = self._farm_saved_deadline()
        if deadline is not None:
            now = utc_now()
            if deadline > now:
                self._set_farm_status(
                    f"Автофарм · следующая разведка в {deadline.astimezone().strftime('%H:%M:%S')} "
                    f"· осталось {_remaining_text(deadline, now)}",
                    topbar=False,
                )
                return
            self._farm_clear_deadline()
            self.logger.info("Автофарм: таймер волны завершён; запускаю новую разведку")

        return original_auto_cycle(self)

    app_class.__init__ = init
    app_class._build_queue_page = build_queue_page
    app_class._auto_cycle = auto_cycle
    app_class._farm_send_wave = send_wave
    app_class._set_farm_status = set_status
    app_class._farm_buffer_minutes = buffer_minutes
    app_class._farm_saved_deadline = saved_deadline
    app_class._farm_save_deadline = save_deadline
    app_class._farm_clear_deadline = clear_deadline
    app_class._farm_save_buffer = save_buffer
    _INSTALLED_CLASSES.add(app_class)
