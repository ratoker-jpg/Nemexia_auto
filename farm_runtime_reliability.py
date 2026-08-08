from __future__ import annotations

from typing import Any

import tkinter as tk

from browser import BrowserAutomationError, CaptchaRequiredError
from farm_flight_classification_fix import _farm_attacks, _slot_flights
from resource_farm_auto import FARM_MIN_MINERALS
from visual_system import (
    BORDER_1,
    BUTTON_SPECS,
    FONT_BODY_STRONG,
    FONT_CAPTION,
    SPACE_MD,
    SPACE_SM,
    SUCCESS,
    SURFACE_2,
    TEXT_1,
    TEXT_2,
    TEXT_3,
    make_button,
)


_CAPACITY_INSTALLED_CLASSES: set[type[Any]] = set()
_UI_INSTALLED_CLASSES: set[type[Any]] = set()


def _walk(root: tk.Misc) -> list[tk.Misc]:
    result: list[tk.Misc] = []
    pending = list(root.winfo_children())
    while pending:
        widget = pending.pop(0)
        result.append(widget)
        try:
            pending.extend(widget.winfo_children())
        except Exception:
            pass
    return result


async def _read_game_fleet_capacity(self: Any) -> dict[str, int]:
    """Read Nemexia's own fleet counter instead of deriving capacity from table rows.

    The game exposes these values directly on fleets.php as #FleetsCount and
    #MaxFleets. Incoming/alliance traffic may be rendered in the same table while
    not consuming one of the player's slots, so the counter is the authority.
    """
    page = await self._ensure_fleets_page()
    values = await page.evaluate(
        r"""() => {
            const parse = (selector) => {
                const raw=(document.querySelector(selector)?.textContent||'').replace(/\s+/g,'');
                const value=Number.parseInt(raw, 10);
                return Number.isFinite(value) ? value : null;
            };
            return {used: parse('#FleetsCount'), max: parse('#MaxFleets')};
        }"""
    )
    try:
        used = int(values.get("used"))
        maximum = int(values.get("max"))
    except Exception as exc:
        raise BrowserAutomationError(
            "Не удалось прочитать игровой лимит флота (Полёты / Макс. флота). "
            "Автофарм остановлен, чтобы не превысить лимит."
        ) from exc
    if used < 0 or maximum <= 0:
        raise BrowserAutomationError(
            f"Некорректный игровой лимит флота: {used}/{maximum}. Автофарм остановлен."
        )
    return {"used": used, "max": maximum, "free": max(0, maximum - used)}


def install_farm_capacity_fix(browser_class: type[Any], app_class: type[Any]) -> None:
    """Make the auto-farm send wave obey the live game fleet counter.

    This installer must run after farm_flight_classification_fix and before
    farm_wave_cooldown so the cooldown wrapper captures this implementation.
    """
    if app_class in _CAPACITY_INSTALLED_CLASSES:
        return

    browser_class.read_fleet_capacity = _read_game_fleet_capacity

    def send_wave(self: Any) -> None:
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

        configured_max = max(1, self._safe_int(self.max_slots_var, 15))
        pairs = pairs[:configured_max]
        if not pairs:
            self._set_farm_status("Автофарм · очередь 500k пуста")
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
            await self._farm_assert_no_captcha("CAPTCHA перед отправкой волны")

            capacity_before = await self.worker.read_fleet_capacity()
            all_before = list(await self.worker.sync_all_flights())
            slot_before = _slot_flights(all_before)
            farm_before = _farm_attacks(all_before, home)

            # The in-game counter is the physical limit. The configured value is
            # retained as an optional lower safety cap when the user deliberately
            # sets it below the game's maximum.
            effective_max = min(int(capacity_before["max"]), configured_max)
            free = max(0, effective_max - int(capacity_before["used"]))
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

            if any(kind for _, _, _, kind in results):
                try:
                    capacity_after = await self.worker.read_fleet_capacity()
                except Exception:
                    capacity_after = capacity_before
                return {
                    "slot_flights": slot_before,
                    "farm_attacks": farm_before,
                    "results": results,
                    "capacity_before": capacity_before,
                    "capacity_after": capacity_after,
                    "free_before": free,
                }

            try:
                all_after = list(await self.worker.sync_all_flights())
                capacity_after = await self.worker.read_fleet_capacity()
            except CaptchaRequiredError:
                return {
                    "slot_flights": slot_before,
                    "farm_attacks": farm_before,
                    "results": results,
                    "capacity_before": capacity_before,
                    "capacity_after": capacity_before,
                    "free_before": free,
                    "post_error": "CAPTCHA появилась после отправки волны",
                    "post_error_kind": "captcha",
                }

            return {
                "slot_flights": _slot_flights(all_after),
                "farm_attacks": _farm_attacks(all_after, home),
                "results": results,
                "capacity_before": capacity_before,
                "capacity_after": capacity_after,
                "free_before": free,
            }

        def success(payload: dict[str, Any]) -> None:
            sent = 0
            processed: set[int] = set()
            error_text = str(payload.get("post_error") or "").strip() or None
            error_kind = str(payload.get("post_error_kind") or "").strip() or None

            for item_id, result, error, kind in list(payload.get("results") or []):
                item_id = int(item_id)
                processed.add(item_id)
                if result:
                    self.db.add_history(result, "sent")
                    self.db.set_queue_state(item_id, "done")
                    self.db.update_timing(
                        result["target"],
                        result["one_way_seconds"],
                        result["round_trip_seconds"],
                        result.get("gas_needed"),
                    )
                    sent += 1
                    self.logger.info("Автофарм: отправлен рейс на %s", result["target"])
                else:
                    error_text = str(error or "Неизвестная ошибка")
                    error_kind = str(kind or "send")
                    self.db.set_queue_state(
                        item_id,
                        "queued" if error_kind == "captcha" else "failed",
                    )
                    break

            for item in items:
                if item.id not in processed:
                    self.db.set_queue_state(item.id, "queued")

            slot_flights = list(payload.get("slot_flights") or [])
            farm_attacks = list(payload.get("farm_attacks") or [])
            capacity_before = dict(payload.get("capacity_before") or {})
            capacity_after = dict(payload.get("capacity_after") or capacity_before)
            self.active_flights = slot_flights

            if capacity_after:
                self._game_fleet_used = int(capacity_after.get("used", 0))
                self._game_fleet_max = int(capacity_after.get("max", configured_max))

            self.render_all()

            if error_text:
                self._stop_farm(
                    error_text,
                    captcha=error_kind == "captcha",
                    do_notify=True,
                )
                return

            if sent:
                latest = max((flight.return_at for flight in farm_attacks if flight.return_at), default=None)
                suffix = ""
                if latest:
                    try:
                        suffix = f" · последний возврат {latest.astimezone().strftime('%H:%M:%S')}"
                    except Exception:
                        pass
                used = int(capacity_after.get("used", 0))
                maximum = int(capacity_after.get("max", configured_max))
                self._set_farm_status(
                    f"Автофарм · отправлено {sent} рейсов · полёты {used}/{maximum}"
                    f" · ждём возврата своих атак{suffix}"
                )
                self.logger.info(
                    "Автофарм: волна отправлена, рейсов=%s, игровой лимит=%s/%s, "
                    "табличных собственных полётов=%s",
                    sent, used, maximum, len(slot_flights),
                )
                self.render_all()
                return

            free_before = int(payload.get("free_before") or 0)
            if free_before <= 0:
                used = int(capacity_before.get("used", 0))
                maximum = int(capacity_before.get("max", configured_max))
                self._set_farm_status(
                    f"Автофарм · нет свободных слотов · игра показывает {used}/{maximum}"
                )
                self.render_all()
                return

            self._stop_farm("Не удалось отправить ни одного рейса", do_notify=True)

        def error(exc: Exception) -> None:
            for item in items:
                self.db.set_queue_state(item.id, "queued")
            self._stop_farm(
                str(exc),
                captcha=isinstance(exc, CaptchaRequiredError),
                do_notify=True,
            )

        self.run_task(
            operation(),
            f"Автофарм · проверяю игровой лимит и отправляю до {len(targets)} рейсов…",
            success,
            error,
            silent=True,
        )

    app_class._farm_send_wave = send_wave
    _CAPACITY_INSTALLED_CLASSES.add(app_class)


def install_farm_ui_fix(app_class: type[Any]) -> None:
    """Give auto-farm its own full-width card and keep button state truthful.

    This installer must run after farm_wave_cooldown so the buffer variable/trace
    already exist when the page is constructed.
    """
    if app_class in _UI_INSTALLED_CLASSES:
        return

    original_build_queue_page = app_class._build_queue_page
    original_render_all = app_class.render_all

    def sync_button(self: Any) -> None:
        button = getattr(self, "farm_auto_button", None)
        if button is None:
            return
        enabled = bool(self.auto_var.get())
        spec = BUTTON_SPECS["danger" if enabled else "success"]
        try:
            button.configure(
                text="Остановить автофарм" if enabled else "Запустить автофарм 500k",
                bg=spec.background,
                fg=spec.foreground,
                activebackground=spec.hover,
                activeforeground=spec.foreground,
                highlightbackground=spec.background,
            )
        except Exception:
            pass

    def build_queue_page(self: Any) -> None:
        original_build_queue_page(self)
        page = self.pages.get("queue")
        old_button = getattr(self, "farm_auto_button", None)
        status_var = getattr(self, "farm_status_var", None)
        buffer_var = getattr(self, "farm_return_buffer_var", None)
        if page is None or old_button is None or status_var is None or buffer_var is None:
            return

        old_master = old_button.master
        try:
            old_button.pack_forget()
        except Exception:
            pass

        # Hide the old inline status label which shared the SEND row and was
        # clipped as soon as the window became narrower.
        for widget in _walk(old_master):
            if widget is old_button:
                continue
            try:
                if isinstance(widget, tk.Label) and str(widget.cget("textvariable")) == str(status_var):
                    widget.pack_forget()
            except Exception:
                pass

        old_buffer = getattr(self, "farm_buffer_frame", None)
        if old_buffer is not None:
            try:
                old_buffer.pack_forget()
            except Exception:
                pass

        existing = list(page.winfo_children())
        before = existing[1] if len(existing) > 1 else None

        card = tk.Frame(
            page,
            bg=SURFACE_2,
            highlightbackground=BORDER_1,
            highlightthickness=1,
        )
        pack_args: dict[str, Any] = {"fill": "x", "pady": (0, SPACE_MD)}
        if before is not None:
            pack_args["before"] = before
        card.pack(**pack_args)
        self.farm_controls_card = card

        tk.Label(
            card,
            text="АВТОФАРМ 500K",
            bg=SURFACE_2,
            fg=TEXT_3,
            font=FONT_CAPTION,
            anchor="w",
        ).pack(fill="x", padx=SPACE_MD, pady=(SPACE_MD, SPACE_SM))

        controls = tk.Frame(card, bg=SURFACE_2)
        controls.pack(fill="x", padx=SPACE_MD)

        self.farm_auto_button = make_button(
            controls,
            "Запустить автофарм 500k",
            self.toggle_farm_auto,
            "success",
            size="compact",
        )
        self.farm_auto_button.pack(side="left", padx=(0, SPACE_MD))

        buffer_block = tk.Frame(controls, bg=SURFACE_2)
        buffer_block.pack(side="left")
        tk.Label(
            buffer_block,
            text="Буфер после возврата, мин",
            bg=SURFACE_2,
            fg=TEXT_2,
            font=FONT_CAPTION,
        ).pack(side="left", padx=(0, 6))
        tk.Spinbox(
            buffer_block,
            from_=0,
            to=60,
            increment=1,
            width=4,
            textvariable=buffer_var,
            justify="center",
        ).pack(side="left")

        status = tk.Label(
            card,
            textvariable=status_var,
            bg=SURFACE_2,
            fg=TEXT_2,
            font=FONT_BODY_STRONG,
            anchor="w",
            justify="left",
        )
        status.pack(fill="x", padx=SPACE_MD, pady=(SPACE_SM, SPACE_MD))
        self.farm_status_label = status

        def resize_status(event: Any) -> None:
            try:
                status.configure(wraplength=max(320, int(event.width) - 2 * SPACE_MD))
            except Exception:
                pass

        card.bind("<Configure>", resize_status, add="+")
        self._sync_farm_button_state()

    def render_all(self: Any) -> None:
        original_render_all(self)
        self._sync_farm_button_state()
        used = getattr(self, "_game_fleet_used", None)
        maximum = getattr(self, "_game_fleet_max", None)
        if used is not None and maximum is not None and hasattr(self, "card_slots_var"):
            try:
                self.card_slots_var.set(f"{int(used)} / {int(maximum)}")
            except Exception:
                pass

    app_class._build_queue_page = build_queue_page
    app_class.render_all = render_all
    app_class._sync_farm_button_state = sync_button
    _UI_INSTALLED_CLASSES.add(app_class)
