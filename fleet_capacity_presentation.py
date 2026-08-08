from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from farm_flight_classification_fix import _farm_attacks
from models import utc_now
from ui_utils import remaining


_INSTALLED_CLASSES: set[type[Any]] = set()


def install_fleet_capacity_presentation(app_class: type[Any]) -> None:
    """Keep capacity and auto-farm attack timing as separate concepts in the UI.

    Capacity comes from Nemexia's #FleetsCount/#MaxFleets counters. Return timing
    uses only normal attacks originating from the configured main/farm planet, so
    recycling/transport/gas and incoming attacks may consume/show elsewhere but
    never become the dashboard's farm-return timer.
    """
    if app_class in _INSTALLED_CLASSES:
        return

    original_render_dashboard = app_class.render_dashboard

    def sync_flights(self: Any, silent: bool = False) -> None:
        endpoint = self.endpoint()

        async def operation() -> dict[str, Any]:
            await self.worker.connect(endpoint)
            flights = list(await self.worker.sync_all_flights())
            capacity = dict(await self.worker.read_fleet_capacity())
            return {"flights": flights, "capacity": capacity}

        def success(payload: dict[str, Any]) -> None:
            flights = list(payload.get("flights") or [])
            capacity = dict(payload.get("capacity") or {})
            self.connected = True
            self.active_flights = flights
            imported = self.db.sync_history_from_flights(flights)
            used = int(capacity.get("used", 0))
            maximum = int(capacity.get("max", self._safe_int(self.max_slots_var, 15)))
            self._game_fleet_used = used
            self._game_fleet_max = maximum
            self.status_var.set(f"Подключено · полёты: {used}/{maximum}")
            self.logger.info(
                "Синхронизированы полёты: строк=%s, игровой счётчик=%s/%s",
                len(flights), used, maximum,
            )
            if imported:
                self.logger.info("Добавлено рейсов из активных атак: %s", imported)
                self.reload_data()
            self.render_all()

        def error(_: Exception) -> None:
            self.connected = False

        self.run_task(operation(), "Синхронизация полётов…", success, error, silent=silent)

    def render_dashboard(self: Any) -> None:
        original_render_dashboard(self)

        used = getattr(self, "_game_fleet_used", None)
        maximum = getattr(self, "_game_fleet_max", None)
        if used is not None and maximum is not None:
            self.card_slots_var.set(f"{int(used)} / {int(maximum)}")

        attacks = _farm_attacks(list(self.active_flights), self.home())
        now = utc_now()
        next_return = min(
            (flight.return_at for flight in attacks if flight.return_at),
            default=None,
        )
        self.card_return_var.set(remaining(next_return, now))

        # The dashboard section is explicitly titled "Активные атаки". Re-render
        # it from our outbound attacks from the configured main planet only.
        # The dedicated Active page can still show the broader own mission list.
        tree = getattr(self, "dashboard_active_tree", None)
        if tree is not None:
            for item_id in tree.get_children(""):
                tree.delete(item_id)
            for flight in sorted(
                attacks,
                key=lambda item: item.return_at or datetime.max.replace(tzinfo=timezone.utc),
            ):
                tree.insert(
                    "",
                    "end",
                    values=(
                        flight.target,
                        remaining(flight.arrival_at, now),
                        remaining(flight.return_at, now),
                    ),
                )

    app_class.sync_flights = sync_flights
    app_class.render_dashboard = render_dashboard
    _INSTALLED_CLASSES.add(app_class)
