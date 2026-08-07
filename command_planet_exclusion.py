from __future__ import annotations

from typing import Any

from browser import BrowserWorker
from storage import Database


COMMAND_PLANET_COORD = "2:5:6"
_INSTALLED = False


def _coord(value: Any) -> str:
    return str(value or "").replace(" ", "")


def is_command_planet_flight(flight: Any) -> bool:
    """True when either side of a flight is the unrelated command planet."""
    return (
        _coord(getattr(flight, "source", "")) == COMMAND_PLANET_COORD
        or _coord(getattr(flight, "target", "")) == COMMAND_PLANET_COORD
    )


def is_command_planet_result(result: dict[str, Any]) -> bool:
    return (
        _coord(result.get("source")) == COMMAND_PLANET_COORD
        or _coord(result.get("target")) == COMMAND_PLANET_COORD
    )


def install_command_planet_exclusion() -> None:
    """Exclude 2:5:6 from active-flight and raid-history calculations globally.

    The game mixes command-planet traffic into the same flight table as the user's
    own missions. This filter keeps those rows out of dashboard counts, slot usage,
    return timers, auto-farm decisions, asteroid/debris capacity calculations, and
    history-derived raid calculations.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_sync_all_flights = BrowserWorker.sync_all_flights
    original_add_history = Database.add_history

    async def sync_all_flights(self: BrowserWorker):
        flights = await original_sync_all_flights(self)
        return [flight for flight in flights if not is_command_planet_flight(flight)]

    def add_history(
        self: Database,
        result: dict[str, Any],
        status: str = "sent",
        error: str | None = None,
    ) -> int | None:
        if is_command_planet_result(result):
            return None
        return original_add_history(self, result, status=status, error=error)

    def list_history(self: Database, limit: int = 1000):
        return self.conn.execute(
            """
            SELECT * FROM history
            WHERE COALESCE(REPLACE(source, ' ', ''), '') <> ?
              AND REPLACE(target, ' ', '') <> ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (COMMAND_PLANET_COORD, COMMAND_PLANET_COORD, int(limit)),
        ).fetchall()

    def last_raid_map(self: Database):
        rows = self.conn.execute(
            """
            SELECT target, MAX(sent_at) AS sent_at
            FROM history
            WHERE status='sent'
              AND COALESCE(REPLACE(source, ' ', ''), '') <> ?
              AND REPLACE(target, ' ', '') <> ?
            GROUP BY target
            """,
            (COMMAND_PLANET_COORD, COMMAND_PLANET_COORD),
        ).fetchall()
        from models import parse_dt

        return {row["target"]: parse_dt(row["sent_at"]) for row in rows if row["sent_at"]}

    BrowserWorker.sync_all_flights = sync_all_flights
    Database.add_history = add_history
    Database.list_history = list_history
    Database.last_raid_map = last_raid_map
    _INSTALLED = True
