from __future__ import annotations

import asyncio
import time
from typing import Any

from browser import BrowserAutomationError, CaptchaRequiredError
from resource_farm_auto import FARM_MIN_MINERALS, _farm_targets
from storage import is_protected_coord


_INSTALLED_CLASSES: set[type[Any]] = set()


def _coord(value: Any) -> str:
    return str(value or "").replace(" ", "")


def _mission(flight: Any) -> str:
    return str(getattr(flight, "mission", "") or "").strip().casefold()


def _farm_attacks(flights: list[Any], home: tuple[int, int, int]) -> list[Any]:
    """Only our outbound normal raids from the configured farm planet block the next farm cycle."""
    source = ":".join(map(str, home))
    return [
        flight for flight in flights
        if _mission(flight) == "атака" and _coord(getattr(flight, "source", "")) == source
    ]


def _slot_flights(flights: list[Any]) -> list[Any]:
    """Flights that consume our fleet capacity.

    Nemexia renders incoming `Атака Солнца` in the same table, but the game's own
    `Полёты: N / Макс. флота` counter does not count it as one of our fleet slots.
    Other missions, including recycling, still occupy a slot.
    """
    return [flight for flight in flights if _mission(flight) != "атака солнца"]


def install_farm_flight_classification_fix(app_class: type[Any]) -> None:
    if app_class in _INSTALLED_CLASSES:
        return

    def auto_cycle(self: Any) -> None:
        if not self.auto_var.get() or self.asteroid_auto_var.get() or self.busy:
            return

        idle_until = float(getattr(self, "_farm_idle_until", 0.0) or 0.0)
        if idle_until > time.monotonic():
            seconds = max(1, int(idle_until - time.monotonic()))
            self._set_farm_status(
                f"Автофарм · подходящих целей нет · повтор через {(seconds + 59) // 60} мин",
                topbar=False,
            )
            return

        endpoint = self.endpoint()
        home = self.home()

        async def operation() -> dict[str, Any]:
            await self.worker.connect(endpoint)
            await self._farm_assert_no_captcha("Nemexia открыла проверку активности")

            all_flights = list(await self.worker.sync_all_flights())
            slot_flights = _slot_flights(all_flights)
            farm_attacks = _farm_attacks(all_flights, home)
            if farm_attacks:
                return {
                    "phase": "waiting",
                    "slot_flights": slot_flights,
                    "farm_attacks": farm_attacks,
                }

            await self._farm_assert_no_captcha("CAPTCHA перед обновлением разведки")
            try:
                old_reports = await self.worker.collect_spy_reports()
            except Exception:
                if await self.worker.captcha_present():
                    raise CaptchaRequiredError("CAPTCHA появилась при чтении старой разведки")
                raise

            deletable_ids = [
                report.message_id for report in old_reports
                if report.message_id and not is_protected_coord(report.coord)
            ]
            if deletable_ids:
                await self.worker.delete_spy_messages(deletable_ids)
            await self._farm_assert_no_captcha("CAPTCHA появилась при очистке разведки")

            await self.worker.request_all_spy_reports()
            await asyncio.sleep(1.0)
            await self._farm_assert_no_captcha("CAPTCHA появилась при запросе новой разведки")
            try:
                reports = await self.worker.collect_spy_reports()
            except Exception:
                if await self.worker.captcha_present():
                    raise CaptchaRequiredError("CAPTCHA появилась при чтении новой разведки")
                raise
            await self._farm_assert_no_captcha("CAPTCHA появилась при чтении новой разведки")
            if not reports:
                raise BrowserAutomationError(
                    "Новая разведка не получена. Локальные данные не очищены; автофарм остановлен."
                )
            return {
                "phase": "refreshed",
                "slot_flights": slot_flights,
                "farm_attacks": [],
                "deleted": len(deletable_ids),
                "reports": reports,
            }

        def success(payload: dict[str, Any]) -> None:
            slot_flights = list(payload.get("slot_flights") or [])
            farm_attacks = list(payload.get("farm_attacks") or [])
            self.active_flights = slot_flights

            if payload.get("phase") == "waiting":
                latest = max((flight.return_at for flight in farm_attacks if flight.return_at), default=None)
                suffix = ""
                if latest:
                    try:
                        suffix = f" · последний возврат {latest.astimezone().strftime('%H:%M:%S')}"
                    except Exception:
                        pass
                self._set_farm_status(
                    f"Автофарм · ждём возврата {len(farm_attacks)} своих атак{suffix}"
                )
                self.render_all()
                return

            reports = list(payload["reports"])
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
                "дубли=%s, обновлено=%s, целей 500k=%s, занято своих слотов=%s",
                payload.get("deleted", 0), cleared, inserted, duplicates, updated,
                len(candidates), len(slot_flights),
            )
            self.render_all()

            if not candidates:
                retry_minutes = max(1, self._safe_int(self.repeat_minutes_var, 60))
                self._farm_idle_until = time.monotonic() + retry_minutes * 60
                self._set_farm_status(
                    f"Автофарм · целей с 500 000 минералов нет · повтор через {retry_minutes} мин"
                )
                self.render_all()
                return

            self._farm_idle_until = 0.0
            self._set_farm_status(
                f"Автофарм · найдено {len(candidates)} целей 500k · отправляю волну"
            )
            self.after(100, self._farm_send_wave)

        def error(exc: Exception) -> None:
            self._stop_farm(
                str(exc),
                captcha=isinstance(exc, CaptchaRequiredError),
                do_notify=True,
            )

        self.run_task(
            operation(),
            "Автофарм · обновление разведки…",
            success,
            error,
            silent=True,
        )

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

        max_slots = max(1, self._safe_int(self.max_slots_var, 15))
        pairs = pairs[:max_slots]
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

            all_before = list(await self.worker.sync_all_flights())
            slot_before = _slot_flights(all_before)
            free = max(0, max_slots - len(slot_before))
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
                return {
                    "slot_flights": slot_before,
                    "farm_attacks": _farm_attacks(all_before, home),
                    "results": results,
                }

            try:
                all_after = list(await self.worker.sync_all_flights())
            except CaptchaRequiredError:
                return {
                    "slot_flights": slot_before,
                    "farm_attacks": _farm_attacks(all_before, home),
                    "results": results,
                    "post_error": "CAPTCHA появилась после отправки волны",
                    "post_error_kind": "captcha",
                }
            return {
                "slot_flights": _slot_flights(all_after),
                "farm_attacks": _farm_attacks(all_after, home),
                "results": results,
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
            self.active_flights = slot_flights
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
                self._set_farm_status(
                    f"Автофарм · отправлено {sent} рейсов · ждём возврата своих атак{suffix}"
                )
                self.logger.info(
                    "Автофарм: волна отправлена, рейсов=%s, занято своих слотов=%s",
                    sent, len(slot_flights),
                )
                self.render_all()
                return

            if slot_flights:
                self._set_farm_status(
                    f"Автофарм · нет свободных слотов · занято {len(slot_flights)}/{max_slots}"
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
            f"Автофарм · отправка {len(targets)} рейсов…",
            success,
            error,
            silent=True,
        )

    app_class._auto_cycle = auto_cycle
    app_class._farm_send_wave = send_wave
    _INSTALLED_CLASSES.add(app_class)
