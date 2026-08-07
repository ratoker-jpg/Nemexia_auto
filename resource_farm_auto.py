from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

import tkinter as tk
from tkinter import messagebox

from browser import CaptchaRequiredError
from models import utc_now
from storage import is_protected_coord
from visual_system import FONT_CAPTION, SURFACE_2, TEXT_2, make_button


FARM_MIN_MINERALS = 500_000
_INSTALLED_CLASSES: set[type[Any]] = set()


def _farm_targets(app: Any) -> list[Any]:
    """Fresh, enabled, non-active targets at the 500k mineral cap."""
    active = app._active_coords()
    targets = [
        target for target in app.targets
        if target.enabled
        and not target.blacklisted
        and target.coord not in active
        and target.last_spy_at is not None
        and target.minerals is not None
        and int(target.minerals) >= FARM_MIN_MINERALS
    ]
    targets.sort(key=lambda target: (-(int(target.minerals or 0)), -(int(target.metal or 0)), target.coord))
    return targets


def _walk_widgets(root: tk.Misc) -> list[tk.Misc]:
    pending = list(root.winfo_children())
    result: list[tk.Misc] = []
    while pending:
        widget = pending.pop(0)
        result.append(widget)
        try:
            pending.extend(widget.winfo_children())
        except Exception:
            pass
    return result


def _replace_text(root: tk.Misc, replacements: dict[str, str]) -> None:
    for widget in _walk_widgets(root):
        try:
            current = str(widget.cget("text"))
        except Exception:
            continue
        if current in replacements:
            try:
                widget.configure(text=replacements[current])
            except Exception:
                pass


def install_resource_farm_auto(app_class: type[Any]) -> None:
    """Replace the legacy queue-drain auto mode with the requested 500k-minerals farm loop."""
    if app_class in _INSTALLED_CLASSES:
        return

    original_init = app_class.__init__
    original_build_queue_page = app_class._build_queue_page
    original_build_settings_page = app_class._build_settings_page
    original_render_all = app_class.render_all

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._farm_idle_until = 0.0
        self._farm_status = "Автофарм выключен"
        # Do not migrate an old persisted auto_enabled=True into the new destructive/send mode.
        # Every application launch requires an explicit fresh enable action.
        if self.auto_var.get():
            self.auto_var.set(False)
            self.db.set_setting("auto_enabled", False)
            self.settings["auto_enabled"] = False
        self.render_all()

    def build_queue_page(self: Any) -> None:
        original_build_queue_page(self)
        page = self.pages.get("queue")
        if page is None:
            return
        send_button = None
        for widget in _walk_widgets(page):
            try:
                if str(widget.cget("text")) == "Отправить волну":
                    send_button = widget
                    break
            except Exception:
                continue
        if send_button is None:
            return

        self.farm_status_var = tk.StringVar(value=getattr(self, "_farm_status", "Автофарм выключен"))
        self.farm_auto_button = make_button(
            send_button.master,
            "Запустить автофарм 500k",
            self.toggle_farm_auto,
            "success",
            size="compact",
        )
        self.farm_auto_button.pack(side="left", padx=(12, 6))
        tk.Label(
            send_button.master,
            textvariable=self.farm_status_var,
            bg=SURFACE_2,
            fg=TEXT_2,
            font=FONT_CAPTION,
            anchor="w",
        ).pack(side="left", padx=(8, 0))

    def build_settings_page(self: Any) -> None:
        original_build_settings_page(self)
        page = self.pages.get("settings")
        if page is None:
            return
        _replace_text(page, {
            "Интервал повторного рейса": "Повтор без подходящих целей",
            "сохраняется для истории; на порядок по металлу не влияет":
                "минут до следующей разведки, если целей с 500 000 минералов нет",
            "Автоинтервал": "Проверка возврата",
            "секунд между попытками": "секунд между проверками активных атак",
            "Автоматический режим": "Автофарм 500k",
            "Автоматически отправлять план": "Автоматически обновлять разведку и отправлять 500k минералов",
            "волна из свободных слотов; остановка при ошибке":
                "ждёт возврата всех атак; CAPTCHA или ошибка немедленно останавливают режим",
        })

    def set_farm_status(self: Any, text: str, *, topbar: bool = True) -> None:
        self._farm_status = text
        if hasattr(self, "farm_status_var"):
            self.farm_status_var.set(text)
        if topbar:
            self.status_var.set(text)

    def farm_notify(self: Any, title: str, message: str) -> None:
        try:
            if self.tray.available and self.tray.icon is None:
                self.tray.start()
            self.tray.notify(title, message)
        except Exception:
            pass

    def stop_farm(self: Any, reason: str, *, notify: bool = True, captcha: bool = False) -> None:
        self.auto_var.set(False)
        self.db.set_setting("auto_enabled", False)
        self.settings["auto_enabled"] = False
        self._farm_idle_until = 0.0
        prefix = "Автофарм остановлен: CAPTCHA" if captcha else "Автофарм остановлен"
        self.set_farm_status(f"{prefix} · {reason}")
        self.logger.error("%s: %s", prefix, reason)
        if notify:
            self.farm_notify(prefix, reason)
        self.render_all()

    def toggle_auto(self: Any) -> None:
        if self.auto_var.get():
            ok = messagebox.askyesno(
                "Nemexia Raid Manager",
                "Включить автофарм 500k?\n\n"
                "Цикл будет без дополнительных подтверждений:\n"
                "1) удалить старые шпионские сообщения (кроме защищённых координат);\n"
                "2) запросить и прочитать новую разведку;\n"
                "3) выбрать цели с минералами от 500 000;\n"
                "4) отправить мегатранспортировщики до лимита слотов;\n"
                "5) дождаться возврата всех атак и повторить.\n\n"
                "При CAPTCHA или ошибке автофарм остановится и пришлёт уведомление.",
            )
            if not ok:
                self.auto_var.set(False)
            else:
                if self.asteroid_auto_var.get():
                    self._stop_asteroid_auto(
                        "Астероидное автопродление отключено при запуске автофарма 500k",
                        notify=False,
                    )
                self._farm_idle_until = 0.0
                self._auto_last = 0.0
                self.set_farm_status("Автофарм включён · начинаю цикл")
                self.logger.info("Автофарм 500k включён")
        else:
            self._farm_idle_until = 0.0
            self.set_farm_status("Автофарм выключен")
            self.logger.info("Автофарм 500k выключен пользователем")
        self.db.set_setting("auto_enabled", bool(self.auto_var.get()))
        self.settings["auto_enabled"] = bool(self.auto_var.get())
        self.render_all()

    def toggle_farm_auto(self: Any) -> None:
        self.auto_var.set(not self.auto_var.get())
        self.toggle_auto()

    def render_all(self: Any) -> None:
        original_render_all(self)
        enabled = bool(self.auto_var.get())
        if hasattr(self, "auto_badge"):
            try:
                self.auto_badge.configure(text="АВТОФАРМ ВКЛ" if enabled else "АВТОФАРМ ВЫКЛ")
            except Exception:
                pass
        if hasattr(self, "farm_auto_button"):
            try:
                self.farm_auto_button.configure(
                    text="Остановить автофарм" if enabled else "Запустить автофарм 500k"
                )
            except Exception:
                pass
        if hasattr(self, "farm_status_var"):
            self.farm_status_var.set(getattr(self, "_farm_status", "Автофарм выключен"))

    def auto_cycle(self: Any) -> None:
        """One state-machine tick: wait for attacks, otherwise refresh spy data."""
        if not self.auto_var.get() or self.asteroid_auto_var.get() or self.busy:
            return
        idle_until = float(getattr(self, "_farm_idle_until", 0.0) or 0.0)
        if idle_until > time.monotonic() and not self.active_flights:
            remaining_seconds = max(1, int(idle_until - time.monotonic()))
            self.set_farm_status(
                f"Автофарм · подходящих целей нет · повтор через {remaining_seconds // 60 + 1} мин",
                topbar=False,
            )
            return

        endpoint = self.endpoint()

        async def operation() -> dict[str, Any]:
            await self.worker.connect(endpoint)
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("Nemexia открыла проверку активности")

            flights = await self.worker.sync_flights()
            if flights:
                return {"phase": "waiting", "flights": flights}

            if await self.worker.captcha_present():
                raise CaptchaRequiredError("Nemexia открыла проверку активности")
            old_reports = await self.worker.collect_spy_reports()
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("CAPTCHA появилась при чтении старой разведки")

            deletable_ids = [
                report.message_id for report in old_reports
                if report.message_id and not is_protected_coord(report.coord)
            ]
            deleted = await self.worker.delete_spy_messages(deletable_ids) if deletable_ids else 0
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("CAPTCHA появилась при очистке разведки")

            await self.worker.request_all_spy_reports()
            await asyncio.sleep(1.0)
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("CAPTCHA появилась при запросе новой разведки")
            reports = await self.worker.collect_spy_reports()
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("CAPTCHA появилась при чтении новой разведки")
            return {"phase": "refreshed", "flights": [], "deleted": deleted, "reports": reports}

        def success(payload: dict[str, Any]) -> None:
            phase = str(payload.get("phase") or "")
            flights = list(payload.get("flights") or [])
            self.active_flights = flights
            if phase == "waiting":
                latest = max((flight.return_at for flight in flights if flight.return_at), default=None)
                suffix = ""
                if latest:
                    try:
                        suffix = f" · последний возврат {latest.astimezone().strftime('%H:%M:%S')}"
                    except Exception:
                        suffix = ""
                self.set_farm_status(f"Автофарм · ждём возврата {len(flights)} атак{suffix}")
                self.render_all()
                return

            reports = list(payload.get("reports") or [])
            cleared = self.db.clear_spy_reports()
            inserted, duplicates, updated = self.db.save_spy_reports(reports)
            self.targets = self.db.list_targets()
            self.target_by_coord = {target.coord: target for target in self.targets}

            count = max(1, self._safe_int(self.queue_size_var, 45))
            candidates = _farm_targets(self)[:count]
            self.db.replace_queue([target.coord for target in candidates])
            self.db.set_settings({"queue_size": count, "queue_resource_mode": "minerals"})
            self.settings.update({"queue_size": count, "queue_resource_mode": "minerals"})
            self._queue_resource_mode = "minerals"

            queue = [item for item in self.db.list_queue() if item.state == "queued"]
            max_slots = max(1, self._safe_int(self.max_slots_var, 15))
            self.checked_queue_ids = {item.id for item in queue[:max_slots]}
            self.logger.info(
                "Автофарм: разведка обновлена; удалено=%s, локально очищено=%s, новых=%s, "
                "дубли=%s, обновлено=%s, целей 500k=%s",
                payload.get("deleted", 0), cleared, inserted, duplicates, updated, len(candidates),
            )
            self.render_all()

            if not candidates:
                retry_minutes = max(1, self._safe_int(self.repeat_minutes_var, 60))
                self._farm_idle_until = time.monotonic() + retry_minutes * 60
                self.set_farm_status(
                    f"Автофарм · целей с 500 000 минералов нет · повтор через {retry_minutes} мин"
                )
                self.render_all()
                return

            self._farm_idle_until = 0.0
            self.set_farm_status(f"Автофарм · найдено {len(candidates)} целей 500k · отправляю волну")
            self.after(100, self._farm_send_wave)

        def error(exc: Exception) -> None:
            if isinstance(exc, CaptchaRequiredError):
                self._stop_farm(str(exc), notify=True, captcha=True)
            else:
                self._stop_farm(str(exc), notify=True, captcha=False)

        self.run_task(operation(), "Автофарм · обновление разведки…", success, error, silent=True)

    def farm_send_wave(self: Any) -> None:
        if not self.auto_var.get() or self.busy:
            return
        queue = [item for item in self.db.list_queue() if item.state == "queued"]
        pairs: list[tuple[Any, Any]] = []
        for item in queue:
            target = self.target_by_coord.get(item.coord)
            if (
                target is not None
                and target.enabled
                and not target.blacklisted
                and target.minerals is not None
                and int(target.minerals) >= FARM_MIN_MINERALS
            ):
                pairs.append((item, target))

        max_slots = max(1, self._safe_int(self.max_slots_var, 15))
        pairs = pairs[:max_slots]
        if not pairs:
            self.set_farm_status("Автофарм · очередь 500k пуста")
            return

        items = [item for item, _ in pairs]
        targets = [target for _, target in pairs]
        for item in items:
            self.db.set_queue_state(item.id, "sending")
        self.render_queue()

        endpoint = self.endpoint()
        ship_count = self._safe_int(self.ship_count_var, 25)
        home = self.home()

        async def operation() -> dict[str, Any]:
            await self.worker.connect(endpoint)
            if await self.worker.captcha_present():
                raise CaptchaRequiredError("Nemexia открыла проверку активности перед отправкой")
            flights_before = await self.worker.sync_flights()
            free = max(0, max_slots - len(flights_before))
            results: list[tuple[int, dict[str, Any] | None, str | None, str | None]] = []
            for item, target in pairs[:free]:
                try:
                    result = await self.worker.send_raid(target, ship_count, home)
                    results.append((item.id, result, None, None))
                except CaptchaRequiredError as exc:
                    results.append((item.id, None, str(exc), "captcha"))
                    break
                except Exception as exc:
                    results.append((item.id, None, str(exc), "send"))
                    break

            flights_after = flights_before
            if not any(kind for _, _, _, kind in results):
                try:
                    flights_after = await self.worker.sync_flights()
                except CaptchaRequiredError:
                    # Sends are already recorded below; stop the mode without retrying them.
                    return {
                        "flights": flights_before,
                        "results": results,
                        "post_error": "CAPTCHA появилась после отправки волны",
                        "post_error_kind": "captcha",
                    }
            return {"flights": flights_after, "results": results}

        def success(payload: dict[str, Any]) -> None:
            results = list(payload.get("results") or [])
            sent = 0
            processed: set[int] = set()
            error_text = str(payload.get("post_error") or "").strip() or None
            error_kind = str(payload.get("post_error_kind") or "").strip() or None

            for item_id, result, error, kind in results:
                processed.add(int(item_id))
                if result:
                    self.db.add_history(result, "sent")
                    self.db.set_queue_state(int(item_id), "done")
                    self.db.update_timing(
                        result["target"], result["one_way_seconds"], result["round_trip_seconds"], result.get("gas_needed")
                    )
                    sent += 1
                    self.logger.info("Автофарм: отправлен рейс на %s", result["target"])
                else:
                    error_text = str(error or "Неизвестная ошибка")
                    error_kind = str(kind or "send")
                    self.db.set_queue_state(int(item_id), "queued" if error_kind == "captcha" else "failed")
                    break

            for item in items:
                if item.id not in processed:
                    self.db.set_queue_state(item.id, "queued")

            self.active_flights = list(payload.get("flights") or [])
            self.render_all()
            if error_text:
                self._stop_farm(error_text, notify=True, captcha=error_kind == "captcha")
                return

            if sent:
                latest = max((flight.return_at for flight in self.active_flights if flight.return_at), default=None)
                suffix = ""
                if latest:
                    try:
                        suffix = f" · последний возврат {latest.astimezone().strftime('%H:%M:%S')}"
                    except Exception:
                        pass
                self.set_farm_status(f"Автофарм · отправлено {sent} рейсов · ждём возврата{suffix}")
                self.logger.info("Автофарм: волна отправлена, рейсов=%s", sent)
                self.render_all()
                return

            if self.active_flights:
                self.set_farm_status(f"Автофарм · ждём возврата {len(self.active_flights)} атак")
                self.render_all()
                return
            self._stop_farm("Не удалось отправить ни одного рейса", notify=True)

        def error(exc: Exception) -> None:
            for item in items:
                if item.state == "sending":
                    self.db.set_queue_state(item.id, "queued")
            if isinstance(exc, CaptchaRequiredError):
                self._stop_farm(str(exc), notify=True, captcha=True)
            else:
                self._stop_farm(str(exc), notify=True)

        self.run_task(operation(), f"Автофарм · отправка {len(targets)} рейсов…", success, error, silent=True)

    app_class.__init__ = init
    app_class._build_queue_page = build_queue_page
    app_class._build_settings_page = build_settings_page
    app_class.render_all = render_all
    app_class.toggle_auto = toggle_auto
    app_class.toggle_farm_auto = toggle_farm_auto
    app_class._auto_cycle = auto_cycle
    app_class._farm_send_wave = farm_send_wave
    app_class._set_farm_status = set_farm_status
    app_class._farm_notify = farm_notify
    app_class._stop_farm = stop_farm
    _INSTALLED_CLASSES.add(app_class)
