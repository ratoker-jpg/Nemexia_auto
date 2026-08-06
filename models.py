from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class Target:
    coord: str
    player: str
    energy: int
    g: int
    s: int
    p: int
    enabled: bool = True
    blacklisted: bool = False
    notes: str = ""
    last_report_at: datetime | None = None
    metal: int | None = None
    minerals: int | None = None
    resource_gas: int | None = None
    last_spy_at: datetime | None = None
    last_loot_total: int | None = None
    total_loot: int = 0
    last_raid_at: datetime | None = None
    last_return_at: datetime | None = None
    raid_count: int = 0
    one_way_seconds: int | None = None
    round_trip_seconds: int | None = None
    gas_needed: int | None = None
    updated_at: datetime | None = None

    @property
    def efficiency(self) -> float | None:
        if not self.round_trip_seconds or self.round_trip_seconds <= 0:
            return None
        return self.energy / max(1.0, self.round_trip_seconds / 60.0)

    def score(self, now: datetime, repeat_minutes: int = 60) -> float:
        if not self.enabled or self.blacklisted or self.energy <= 0:
            return -1.0
        trip_minutes = max(1.0, (self.round_trip_seconds or 3600) / 60.0)
        base = self.energy / trip_minutes
        if self.last_raid_at is None:
            freshness = 1.55
        else:
            elapsed = max(0.0, (now - self.last_raid_at).total_seconds() / 60.0)
            freshness = min(2.0, max(0.15, elapsed / max(1, repeat_minutes)))
        return base * freshness

    @classmethod
    def from_row(cls, row: Any) -> "Target":
        return cls(
            coord=row["coord"],
            player=row["player"] or "—",
            energy=int(row["energy"] or 0),
            g=int(row["g"]),
            s=int(row["s"]),
            p=int(row["p"]),
            enabled=bool(row["enabled"]),
            blacklisted=bool(row["blacklisted"]),
            notes=row["notes"] or "",
            last_report_at=parse_dt(row["last_report_at"]),
            metal=row["metal"],
            minerals=row["minerals"],
            resource_gas=row["resource_gas"],
            last_spy_at=parse_dt(row["last_spy_at"]),
            last_loot_total=row["last_loot_total"],
            total_loot=int(row["total_loot"] or 0),
            last_raid_at=parse_dt(row["last_raid_at"]),
            last_return_at=parse_dt(row["last_return_at"]),
            raid_count=int(row["raid_count"] or 0),
            one_way_seconds=row["one_way_seconds"],
            round_trip_seconds=row["round_trip_seconds"],
            gas_needed=row["gas_needed"],
            updated_at=parse_dt(row["updated_at"]),
        )


@dataclass(slots=True)
class Flight:
    fleet_id: str | None
    source: str
    target: str
    mission: str
    arrival_at: datetime | None
    return_at: datetime | None
    sent_at: datetime | None = None
    ship_count: int | None = None
    player: str = "—"
    sent_at_source: str = "unknown"


@dataclass(slots=True)
class QueueItem:
    id: int
    coord: str
    position: int
    state: str
    created_at: datetime | None


@dataclass(slots=True)
class SpyReport:
    coord: str
    player: str
    energy: int
    report_at: datetime | None = None
    message_id: str | None = None
    metal: int | None = None
    minerals: int | None = None
    gas: int | None = None
    population: int | None = None
    ships: int | None = None
    defense: int | None = None
    completeness: str | None = None
    raw_payload: str = ""


@dataclass(slots=True)
class CombatReport:
    coord: str
    report_at: datetime | None = None
    message_id: str | None = None
    attack_at: datetime | None = None
    result: str | None = None
    metal: int | None = None
    minerals: int | None = None
    gas: int | None = None
    source: str = "messages"
    raw_payload: str = ""

    @property
    def total_loot(self) -> int:
        return sum(value or 0 for value in (self.metal, self.minerals, self.gas))


@dataclass(slots=True)
class AsteroidObservation:
    g: int
    s: int
    p: int
    last_move_server: datetime
    next_move_server: datetime
    period_seconds: int
    scanned_server_at: datetime
    tooltip_html: str = ""
    status: str = "found"
    error: str | None = None

    @property
    def coord(self) -> str:
        return f"{self.g}:{self.s}:{self.p}"


@dataclass(slots=True)
class AsteroidPlan:
    observation: AsteroidObservation
    target_g: int
    target_s: int
    target_p: int
    shifts: int
    one_way_seconds: int
    round_trip_seconds: int
    arrival_server_at: datetime
    return_server_at: datetime
    gas_needed: int | None = None
    status: str = "ready"
    error: str | None = None

    @property
    def target_coord(self) -> str:
        return f"{self.target_g}:{self.target_s}:{self.target_p}"
