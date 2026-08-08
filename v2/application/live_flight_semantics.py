from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from v2.application.flight_source import ActiveFlightSnapshot
from v2.domain.flights import (
    AccountContext,
    ClassifiedFlight,
    FlightFacts,
    classify_flight,
    normalize_coord,
)


LEGACY_COMMAND_PLANET = "2:5:6"


@dataclass(frozen=True)
class LiveFlightPolicy:
    """Account-owned coordinates and exclusions used only for classification."""

    owned_planets: frozenset[str]
    command_planets: frozenset[str]
    ignored_coords: frozenset[str]
    farm_home: str | None

    def account_context(self) -> AccountContext:
        return AccountContext(
            owned_planets=self.owned_planets,
            command_planets=self.command_planets,
            ignored_coords=self.ignored_coords,
            farm_home=self.farm_home,
        )


@dataclass(frozen=True)
class ClassifiedActiveFlight:
    raw: ActiveFlightSnapshot
    facts: ClassifiedFlight


def _setting_coord(settings: Mapping[str, object], prefix: str) -> str | None:
    try:
        parts = tuple(int(settings[f"{prefix}_{axis}"]) for axis in ("g", "s", "p"))
    except (KeyError, TypeError, ValueError):
        return None
    if any(part <= 0 for part in parts):
        return None
    return ":".join(str(part) for part in parts)


def build_live_flight_policy(
    settings: Mapping[str, object],
    *,
    owned_planets: Iterable[str] = (),
    command_planets: Iterable[str] = (LEGACY_COMMAND_PLANET,),
    ignored_coords: Iterable[str] = (),
) -> LiveFlightPolicy:
    """Build classification policy without mutating legacy settings.

    The persisted legacy `home_g/home_s/home_p` triplet is the currently verified
    farm-home source. Additional owned planets are supplied by read-only live facts
    when available. The historic command planet is centralized here instead of
    being duplicated across UI/browser code.
    """

    farm_home = _setting_coord(settings, "home")
    owned = {normalize_coord(coord) for coord in owned_planets if normalize_coord(coord)}
    if farm_home:
        owned.add(farm_home)
    return LiveFlightPolicy(
        owned_planets=frozenset(owned),
        command_planets=frozenset(
            normalize_coord(coord) for coord in command_planets if normalize_coord(coord)
        ),
        ignored_coords=frozenset(
            normalize_coord(coord) for coord in ignored_coords if normalize_coord(coord)
        ),
        farm_home=farm_home,
    )


def classify_active_flights(
    flights: Iterable[ActiveFlightSnapshot],
    policy: LiveFlightPolicy,
) -> tuple[ClassifiedActiveFlight, ...]:
    context = policy.account_context()
    return tuple(
        ClassifiedActiveFlight(
            raw=flight,
            facts=classify_flight(
                FlightFacts(source=flight.source, target=flight.target, mission=flight.mission),
                context,
            ),
        )
        for flight in flights
    )
