from __future__ import annotations

from datetime import datetime
from typing import Any

from browser import BrowserWorker
from storage import Database


_ORIGINAL_DATABASE_INIT = Database.__init__
_ORIGINAL_ADD_HISTORY = Database.add_history
_ORIGINAL_SYNC_ALL_FLIGHTS = BrowserWorker.sync_all_flights
_INSTALLED = False
_VALID_SOURCES = {"exact", "inferred", "unknown"}


def _infer_sent_at(arrival_at: datetime | None, return_at: datetime | None) -> datetime | None:
    """Infer send time only for a valid ordered arrival/return pair.

    The value is never called exact because the formula assumes equal outbound and
    return durations: sent = arrival - (return - arrival).
    """
    if arrival_at is None or return_at is None or return_at <= arrival_at:
        return None
    return arrival_at + (arrival_at - return_at)


def _derive_sent_at_source(result: dict[str, Any]) -> str:
    explicit = str(result.get("sent_at_source") or "").strip().casefold()
    if explicit in _VALID_SOURCES:
        return explicit
    if not result.get("sent_at"):
        return "unknown"
    if result.get("one_way_seconds") is not None or result.get("round_trip_seconds") is not None:
        return "exact"
    return "inferred"


def _database_init_with_provenance(self: Database, *args, **kwargs) -> None:
    _ORIGINAL_DATABASE_INIT(self, *args, **kwargs)
    columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(history)")}
    if "sent_at_source" not in columns:
        self.conn.execute(
            "ALTER TABLE history ADD COLUMN sent_at_source TEXT NOT NULL DEFAULT 'unknown'"
        )
    self.conn.execute(
        """
        UPDATE history
        SET sent_at_source = CASE
            WHEN sent_at IS NULL OR sent_at = '' THEN 'unknown'
            WHEN one_way_seconds IS NOT NULL OR round_trip_seconds IS NOT NULL THEN 'exact'
            ELSE 'inferred'
        END
        WHERE sent_at_source IS NULL OR sent_at_source = '' OR sent_at_source = 'unknown'
        """
    )
    self.conn.commit()


def _add_history_with_provenance(
    self: Database,
    result: dict[str, Any],
    status: str = "sent",
    error: str | None = None,
) -> int | None:
    payload = dict(result)
    source = _derive_sent_at_source(payload)
    payload["sent_at_source"] = source
    row_id = _ORIGINAL_ADD_HISTORY(self, payload, status=status, error=error)
    if row_id is not None:
        self.conn.execute(
            "UPDATE history SET sent_at_source=? WHERE id=?",
            (source, int(row_id)),
        )
        self.conn.commit()
    return row_id


async def _sync_all_flights_with_provenance(self: BrowserWorker):
    flights = await _ORIGINAL_SYNC_ALL_FLIGHTS(self)
    for flight in flights:
        inferred = _infer_sent_at(flight.arrival_at, flight.return_at)
        if inferred is None:
            flight.sent_at = None
            flight.sent_at_source = "unknown"
        else:
            flight.sent_at = inferred
            flight.sent_at_source = "inferred"
    return flights


def _is_attack(flight: Any) -> bool:
    return str(getattr(flight, "mission", "") or "").strip().casefold() == "атака"


def _sync_history_with_provenance(self: Database, flights) -> int:
    inserted = 0
    for flight in flights:
        if not _is_attack(flight):
            continue
        sent_at = getattr(flight, "sent_at", None)
        source = str(getattr(flight, "sent_at_source", "") or "").strip().casefold()
        if source == "inferred" or sent_at is None:
            sent_at = _infer_sent_at(flight.arrival_at, flight.return_at)
            source = "inferred" if sent_at is not None else "unknown"
        if source not in _VALID_SOURCES:
            source = "inferred" if sent_at is not None else "unknown"
        result = {
            "fleet_id": flight.fleet_id,
            "source": flight.source,
            "target": str(flight.target).replace(" ", ""),
            "player": flight.player,
            "sent_at": sent_at.isoformat() if isinstance(sent_at, datetime) else None,
            "sent_at_source": source,
            "arrival_at": flight.arrival_at.isoformat() if flight.arrival_at else None,
            "return_at": flight.return_at.isoformat() if flight.return_at else None,
        }
        status = "sent" if sent_at else "unknown_time"
        if self.add_history(result, status=status, error=None) is not None:
            inserted += 1
    return inserted


def install_flight_time_provenance_fix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    Database.__init__ = _database_init_with_provenance
    Database.add_history = _add_history_with_provenance
    Database.sync_history_from_flights = _sync_history_with_provenance
    BrowserWorker.sync_all_flights = _sync_all_flights_with_provenance
    _INSTALLED = True
