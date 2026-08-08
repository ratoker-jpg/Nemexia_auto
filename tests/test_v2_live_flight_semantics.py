from v2.application.flight_source import ActiveFlightSnapshot
from v2.application.live_flight_semantics import (
    LEGACY_COMMAND_PLANET,
    build_live_flight_policy,
    classify_active_flights,
)
from v2.domain.flights import FlightDirection, FlightOwnerScope


def _flight(source: str, target: str, mission: str) -> ActiveFlightSnapshot:
    return ActiveFlightSnapshot(source=source, target=target, mission=mission)


def test_policy_centralizes_farm_home_and_command_planet() -> None:
    policy = build_live_flight_policy(
        {"home_g": "3", "home_s": 39, "home_p": 11},
        owned_planets={"3:39:8"},
    )
    assert policy.farm_home == "3:39:11"
    assert policy.owned_planets == frozenset({"3:39:11", "3:39:8"})
    assert policy.command_planets == frozenset({LEGACY_COMMAND_PLANET})


def test_only_exact_outbound_attack_from_farm_home_blocks_farm_cycle() -> None:
    policy = build_live_flight_policy(
        {"home_g": 3, "home_s": 39, "home_p": 11},
        owned_planets={"3:39:8"},
    )
    classified = classify_active_flights(
        (
            _flight("3:39:11", "3:1:2", "Атака"),
            _flight("3:39:11", "3:1:3", "Переработка"),
            _flight("3:39:8", "3:1:4", "Атака"),
        ),
        policy,
    )
    assert [item.facts.blocks_farm_cycle for item in classified] == [True, False, False]


def test_command_planet_is_excluded_without_rewriting_personal_ownership() -> None:
    policy = build_live_flight_policy({"home_g": 3, "home_s": 39, "home_p": 11})
    personal = classify_active_flights(
        [_flight("3:39:11", "2:5:6", "Атака")], policy
    )[0].facts
    assert personal.direction is FlightDirection.OUTGOING
    assert personal.owner_scope is FlightOwnerScope.PERSONAL
    assert personal.excluded is True
    assert personal.blocks_farm_cycle is False

    command_only = classify_active_flights(
        [_flight("2:5:6", "9:9:9", "Транспорт")], policy
    )[0].facts
    assert command_only.owner_scope is FlightOwnerScope.COMMAND
    assert command_only.excluded is True
