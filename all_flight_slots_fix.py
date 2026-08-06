from __future__ import annotations

from typing import Any

from browser import BrowserWorker
from storage import Database


_ORIGINAL_SYNC_HISTORY = Database.sync_history_from_flights
_INSTALLED = False


def _is_attack(flight: Any) -> bool:
    return str(getattr(flight, "mission", "") or "").strip().casefold() == "атака"


async def _sync_all_for_capacity(self: BrowserWorker):
    """Return every active mission because Nemexia uses one shared fleet-slot limit."""
    return await self.sync_all_flights()


def _active_attack_coords(self: Any) -> set[str]:
    """Prevent duplicate attacks without treating transport or gas missions as attacks."""
    return {
        str(flight.target).replace(" ", "")
        for flight in self.active_flights
        if _is_attack(flight)
    }


def _sync_history_attacks(self: Database, flights):
    """The raid history remains attack-only even though the UI tracks all occupied slots."""
    return _ORIGINAL_SYNC_HISTORY(self, [flight for flight in flights if _is_attack(flight)])


def _auto_cycle_all_slots(self: Any) -> None:
    queue = [item for item in self.db.list_queue() if item.state == "queued"]
    if not queue:
        return

    endpoint = self.endpoint()
    max_slots = self._safe_int(self.max_slots_var, 15)
    ship_count = self._safe_int(self.ship_count_var, 25)
    home = self.home()

    async def operation():
        await self.worker.connect(endpoint)
        flights = await self.worker.sync_all_flights()
        free = max(0, max_slots - len(flights))
        if free <= 0:
            return flights, []
        active_attacks = {
            str(flight.target).replace(" ", "")
            for flight in flights
            if _is_attack(flight)
        }
        candidates = [item for item in queue if item.coord not in active_attacks][:free]
        results: list[tuple[int, dict[str, Any] | None, str | None]] = []
        for item in candidates:
            target = self.target_by_coord.get(item.coord)
            if target is None or not target.enabled or target.blacklisted:
                results.append((item.id, None, "Цель исключена или отсутствует в базе"))
                break
            try:
                result = await self.worker.send_raid(target, ship_count, home)
                results.append((item.id, result, None))
            except Exception as exc:
                results.append((item.id, None, str(exc)))
                break
        return flights, results

    def success(payload):
        flights, results = payload
        self.active_flights = flights
        if not results:
            self.render_all()
            return
        sent = 0
        error_text: str | None = None
        for item_id, result, error_text in results:
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
                self.logger.info("Авто: отправлен рейс на %s", result["target"])
            else:
                self.db.set_queue_state(item_id, "failed")
                break
        if error_text:
            self.auto_var.set(False)
            self.db.set_setting("auto_enabled", False)
            self.logger.error("Авто остановлено: %s", error_text)
            self.tray.notify("Автоотправка остановлена", error_text)
        if sent:
            self.logger.info("Авто: отправлена волна из %s рейсов", sent)
            self.reload_data()
            self.sync_flights(silent=True)
        else:
            self.render_all()

    def error(exc: Exception) -> None:
        self.auto_var.set(False)
        self.db.set_setting("auto_enabled", False)
        self.logger.error("Авто остановлено: %s", exc)
        self.render_all()

    self.run_task(operation(), "Авто: проверка слотов…", success, error, silent=True)


def install_all_flight_slot_fix(app_class: type[Any]) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    BrowserWorker.sync_flights = _sync_all_for_capacity
    Database.sync_history_from_flights = _sync_history_attacks
    app_class._active_coords = _active_attack_coords
    app_class._auto_cycle = _auto_cycle_all_slots
    _INSTALLED = True
