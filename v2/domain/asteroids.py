from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Sequence


NEMEXIA_SERVER_UTC_OFFSET_HOURS = 4
ASTEROID_POSITIONS_PER_SYSTEM = 24
ASTEROID_MIN_SYSTEM = 1
ASTEROID_MAX_SYSTEM = 40
ASTEROID_SUPPORTED_GALAXIES = (1, 2, 3)
ASTEROID_PLAN_MAX_ITERATIONS = 8
ASTEROID_CANDIDATE_RESERVE = 5
ASTEROID_MAX_CANDIDATES = 200
ASTEROID_DEFAULT_SAFETY_SECONDS = 10
ASTEROID_RECYCLER_SHIP_KEY = "ship_1_11"
ASTEROID_MISSION_CODE = "8"
ASTEROID_MISSION_NAME = "Добыча газа"

SERVER_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M",
)


class AsteroidReadState(str, Enum):
    """Read-only state for an already-open asteroid source."""

    LIVE_UNAVAILABLE = "live_unavailable"
    CAPTCHA = "captcha"
    NO_ASTEROIDS = "no_asteroids"
    READY = "ready"


class AsteroidReadinessState(str, Enum):
    """Pure dispatch-readiness state; V2-51 performs no game mutation."""

    LIVE_UNAVAILABLE = "live_unavailable"
    CAPTCHA = "captcha"
    INVALID_OBSERVATION = "invalid_observation"
    CAPACITY_BLOCKED = "capacity_blocked"
    READY = "ready"


@dataclass(frozen=True)
class AsteroidObservationFact:
    """Minimum immutable observation provenance required by future V2 stages."""

    galaxy: int
    system: int
    position: int
    last_move_at: datetime
    next_move_at: datetime
    period_seconds: int
    observed_at: datetime
    source: str = "galaxy.squareInfo"

    @property
    def coord(self) -> str:
        return f"{self.galaxy}:{self.system}:{self.position}"

    @property
    def structurally_valid(self) -> bool:
        return (
            self.galaxy in ASTEROID_SUPPORTED_GALAXIES
            and ASTEROID_MIN_SYSTEM <= self.system <= ASTEROID_MAX_SYSTEM
            and 1 <= self.position <= ASTEROID_POSITIONS_PER_SYSTEM
            and self.period_seconds > 0
            and _as_utc(self.next_move_at) > _as_utc(self.last_move_at)
        )


@dataclass(frozen=True)
class AsteroidPlanFact:
    """Pure plan result after game timing facts have stabilized."""

    observation: AsteroidObservationFact
    target_galaxy: int
    target_system: int
    target_position: int
    shifts: int
    one_way_seconds: int
    round_trip_seconds: int
    arrival_at: datetime
    return_at: datetime
    gas_needed: int | None
    movement_margin_seconds: float

    @property
    def target_coord(self) -> str:
        return f"{self.target_galaxy}:{self.target_system}:{self.target_position}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def server_wall_clock_to_utc(value: datetime) -> datetime:
    """Interpret Nemexia wall-clock values in the proven server UTC+04 timezone."""

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    server_tz = timezone(timedelta(hours=NEMEXIA_SERVER_UTC_OFFSET_HOURS))
    return value.replace(tzinfo=server_tz).astimezone(timezone.utc)


def parse_server_wall_clock(value: str) -> datetime:
    normalized = " ".join(html_module.unescape(value or "").replace("\xa0", " ").split())
    for fmt in SERVER_DATETIME_FORMATS:
        try:
            return server_wall_clock_to_utc(datetime.strptime(normalized, fmt))
        except ValueError:
            continue
    raise ValueError(f"Unable to parse Nemexia server time: {value!r}")


def parse_asteroid_tooltip(
    tooltip_html: str,
    *,
    galaxy: int,
    system: int,
    position: int,
    observed_server_at: datetime,
) -> AsteroidObservationFact:
    """Parse only the movement facts proven by the legacy squareInfo response."""

    text = re.sub(r"<[^>]+>", " ", tooltip_html or "")
    text = " ".join(html_module.unescape(text).replace("\xa0", " ").split())
    if not re.search(r"информац\w*\s+об\s+астероид", text, re.I):
        raise ValueError("squareInfo response does not contain asteroid information")

    last_match = re.search(
        r"Последнее\s+перемещение\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.I,
    )
    next_match = re.search(
        r"Следующее\s+перемещение\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.I,
    )
    speed_match = re.search(r"Скорость\s+(\d+)\s*Минут", text, re.I)
    if not last_match or not next_match:
        raise ValueError("asteroid movement timestamps are missing")

    last_move = parse_server_wall_clock(last_match.group(1))
    next_move = parse_server_wall_clock(next_match.group(1))
    period_seconds = int((next_move - last_move).total_seconds())
    if period_seconds <= 0 and speed_match:
        period_seconds = int(speed_match.group(1)) * 60
    if period_seconds <= 0:
        raise ValueError("asteroid movement period must be positive")

    observed_at = server_wall_clock_to_utc(observed_server_at)
    # Preserve the effective legacy rule: a saved tooltip may be read just after
    # the announced boundary, so advance the schedule while keeping the visible
    # coordinate as the observation origin.
    while next_move <= observed_at:
        last_move = next_move
        next_move += timedelta(seconds=period_seconds)

    fact = AsteroidObservationFact(
        galaxy=int(galaxy),
        system=int(system),
        position=int(position),
        last_move_at=last_move,
        next_move_at=next_move,
        period_seconds=period_seconds,
        observed_at=observed_at,
    )
    if not fact.structurally_valid:
        raise ValueError("invalid asteroid observation")
    return fact


def advance_coordinate(
    galaxy: int,
    system: int,
    position: int,
    steps: int,
    *,
    max_system: int = ASTEROID_MAX_SYSTEM,
) -> tuple[int, int, int]:
    if galaxy not in ASTEROID_SUPPORTED_GALAXIES:
        raise ValueError("unsupported asteroid galaxy")
    if not (ASTEROID_MIN_SYSTEM <= system <= max_system):
        raise ValueError("invalid asteroid system")
    if not (1 <= position <= ASTEROID_POSITIONS_PER_SYSTEM):
        raise ValueError("invalid asteroid position")
    if steps < 0:
        raise ValueError("reverse asteroid movement is not supported")
    linear = (system - 1) * ASTEROID_POSITIONS_PER_SYSTEM + (position - 1) + int(steps)
    new_system, position_zero = divmod(linear, ASTEROID_POSITIONS_PER_SYSTEM)
    new_system += 1
    if new_system > int(max_system):
        raise ValueError(f"asteroid leaves system {max_system}")
    return int(galaxy), int(new_system), int(position_zero + 1)


def movement_count(
    next_move_at: datetime,
    period_seconds: int,
    arrival_at: datetime,
    *,
    safety_seconds: int = 0,
) -> int:
    if period_seconds <= 0:
        raise ValueError("asteroid movement period must be positive")
    effective_arrival = _as_utc(arrival_at) + timedelta(seconds=max(0, int(safety_seconds)))
    next_move = _as_utc(next_move_at)
    if effective_arrival < next_move:
        return 0
    elapsed = (effective_arrival - next_move).total_seconds()
    return 1 + int(elapsed // int(period_seconds))


def movement_margin_seconds(
    next_move_at: datetime,
    period_seconds: int,
    arrival_at: datetime,
) -> float:
    if period_seconds <= 0:
        raise ValueError("asteroid movement period must be positive")
    arrival = _as_utc(arrival_at)
    next_move = _as_utc(next_move_at)
    if arrival < next_move:
        return (next_move - arrival).total_seconds()
    elapsed = (arrival - next_move).total_seconds()
    remainder = elapsed % int(period_seconds)
    return min(remainder, int(period_seconds) - remainder)


def predict_coordinate(
    observation: AsteroidObservationFact,
    arrival_at: datetime,
    *,
    safety_seconds: int = 0,
) -> tuple[tuple[int, int, int], int]:
    if not observation.structurally_valid:
        raise ValueError("invalid asteroid observation")
    shifts = movement_count(
        observation.next_move_at,
        observation.period_seconds,
        arrival_at,
        safety_seconds=safety_seconds,
    )
    return advance_coordinate(
        observation.galaxy,
        observation.system,
        observation.position,
        shifts,
    ), shifts


def candidate_limit(
    requested: int,
    *,
    reserve: int = ASTEROID_CANDIDATE_RESERVE,
    maximum: int = ASTEROID_MAX_CANDIDATES,
) -> int:
    return min(max(1, int(maximum)), max(1, int(requested)) + max(0, int(reserve)))


def classify_read_state(
    *,
    browser_available: bool,
    captcha_present: bool,
    observations: Sequence[AsteroidObservationFact],
) -> AsteroidReadState:
    if captcha_present:
        return AsteroidReadState.CAPTCHA
    if not browser_available:
        return AsteroidReadState.LIVE_UNAVAILABLE
    if not observations:
        return AsteroidReadState.NO_ASTEROIDS
    return AsteroidReadState.READY


def classify_dispatch_readiness(
    *,
    browser_available: bool,
    captcha_present: bool,
    observation: AsteroidObservationFact | None,
    available_recyclers: int,
    requested_recyclers: int,
    free_fleet_slots: int,
) -> AsteroidReadinessState:
    if captcha_present:
        return AsteroidReadinessState.CAPTCHA
    if not browser_available:
        return AsteroidReadinessState.LIVE_UNAVAILABLE
    if observation is None or not observation.structurally_valid:
        return AsteroidReadinessState.INVALID_OBSERVATION
    if int(requested_recyclers) <= 0:
        return AsteroidReadinessState.INVALID_OBSERVATION
    if int(free_fleet_slots) <= 0 or int(available_recyclers) < int(requested_recyclers):
        return AsteroidReadinessState.CAPACITY_BLOCKED
    return AsteroidReadinessState.READY
