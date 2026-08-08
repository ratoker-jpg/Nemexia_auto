from v2.domain.flights import (
    AccountContext,
    FlightDirection,
    FlightFacts,
    FlightOwnerScope,
    classify_flight,
)


def context() -> AccountContext:
    return AccountContext(
        owned_planets=frozenset({"3:39:11", "3:39:8"}),
        command_planets=frozenset({"2:5:6"}),
        ignored_coords=frozenset({"1:1:1"}),
        farm_home="3:39:11",
    )


def test_outbound_normal_attack_from_farm_home_blocks_cycle() -> None:
    result = classify_flight(
        FlightFacts("3:39:11", "3:10:5", "Атака"),
        context(),
    )
    assert result.direction is FlightDirection.OUTGOING
    assert result.owner_scope is FlightOwnerScope.PERSONAL
    assert result.is_normal_attack
    assert result.blocks_farm_cycle
    assert not result.excluded


def test_other_outbound_mission_does_not_block_farm_timer() -> None:
    result = classify_flight(
        FlightFacts("3:39:11", "3:10:5", "Переработка"),
        context(),
    )
    assert result.direction is FlightDirection.OUTGOING
    assert not result.is_normal_attack
    assert not result.blocks_farm_cycle


def test_incoming_attack_is_not_our_farm_attack() -> None:
    result = classify_flight(
        FlightFacts("1:20:7", "3:39:11", "Атака"),
        context(),
    )
    assert result.direction is FlightDirection.INCOMING
    assert result.is_normal_attack
    assert not result.blocks_farm_cycle


def test_command_planet_is_explicitly_excluded() -> None:
    outbound = classify_flight(
        FlightFacts("2:5:6", "1:31:0", "Атака Солнца"),
        context(),
    )
    inbound = classify_flight(
        FlightFacts("3:39:11", "2:5:6", "Атака"),
        context(),
    )
    assert outbound.owner_scope is FlightOwnerScope.COMMAND
    assert outbound.excluded
    assert inbound.owner_scope is FlightOwnerScope.PERSONAL
    assert inbound.excluded
    assert not inbound.blocks_farm_cycle


def test_whitespace_in_coordinates_is_normalized() -> None:
    result = classify_flight(
        FlightFacts(" 3 : 39 : 11 ", "3:10:5", "  Атака  "),
        context(),
    )
    assert result.source == "3:39:11"
    assert result.blocks_farm_cycle
