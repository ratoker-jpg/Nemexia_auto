from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FlightDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    FOREIGN = "foreign"


class FlightOwnerScope(str, Enum):
    PERSONAL = "personal"
    COMMAND = "command"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AccountContext:
    owned_planets: frozenset[str]
    command_planets: frozenset[str] = frozenset()
    ignored_coords: frozenset[str] = frozenset()
    farm_home: str | None = None


@dataclass(frozen=True)
class FlightFacts:
    source: str
    target: str
    mission: str


@dataclass(frozen=True)
class ClassifiedFlight:
    source: str
    target: str
    mission: str
    direction: FlightDirection
    owner_scope: FlightOwnerScope
    excluded: bool
    is_normal_attack: bool
    blocks_farm_cycle: bool


def normalize_coord(value: str | None) -> str:
    return str(value or "").replace(" ", "")


def normalize_mission(value: str | None) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def normalize_context(context: AccountContext) -> AccountContext:
    return AccountContext(
        owned_planets=frozenset(normalize_coord(coord) for coord in context.owned_planets),
        command_planets=frozenset(normalize_coord(coord) for coord in context.command_planets),
        ignored_coords=frozenset(normalize_coord(coord) for coord in context.ignored_coords),
        farm_home=normalize_coord(context.farm_home) if context.farm_home else None,
    )


def classify_flight(flight: FlightFacts, context: AccountContext) -> ClassifiedFlight:
    """Classify ownership/timing semantics without estimating fleet capacity.

    The current, verified farm rule is deliberately narrow: only an outbound
    mission whose normalized label is exactly `атака` and whose source equals the
    configured farm home blocks the next farm cycle. Physical fleet capacity is
    intentionally absent from this model because V2 must read the game's own
    `FleetsCount / MaxFleets` counter instead of deriving it from table rows.
    """
    ctx = normalize_context(context)
    source = normalize_coord(flight.source)
    target = normalize_coord(flight.target)
    mission = normalize_mission(flight.mission)

    command_related = source in ctx.command_planets or target in ctx.command_planets
    ignored = source in ctx.ignored_coords or target in ctx.ignored_coords
    excluded = command_related or ignored

    if source in ctx.owned_planets:
        direction = FlightDirection.OUTGOING
        owner_scope = FlightOwnerScope.PERSONAL
    elif target in ctx.owned_planets:
        direction = FlightDirection.INCOMING
        owner_scope = FlightOwnerScope.PERSONAL
    else:
        direction = FlightDirection.FOREIGN
        owner_scope = FlightOwnerScope.UNKNOWN

    # Command-planet involvement is an exclusion rule, not an ownership override
    # for an otherwise clearly personal flight. Pure command/foreign traffic is
    # still labelled COMMAND so the UI can explain why it is ignored.
    if command_related and owner_scope is FlightOwnerScope.UNKNOWN:
        owner_scope = FlightOwnerScope.COMMAND

    is_normal_attack = mission == "атака"
    blocks_farm_cycle = bool(
        not excluded
        and is_normal_attack
        and ctx.farm_home
        and source == ctx.farm_home
        and direction is FlightDirection.OUTGOING
    )

    return ClassifiedFlight(
        source=source,
        target=target,
        mission=mission,
        direction=direction,
        owner_scope=owner_scope,
        excluded=excluded,
        is_normal_attack=is_normal_attack,
        blocks_farm_cycle=blocks_farm_cycle,
    )
