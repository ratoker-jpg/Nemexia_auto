from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.domain.asteroids import (
    ASTEROID_CANDIDATE_RESERVE,
    ASTEROID_MAX_CANDIDATES,
    ASTEROID_MAX_SYSTEM,
    ASTEROID_MISSION_CODE,
    ASTEROID_MISSION_NAME,
    ASTEROID_PLAN_MAX_ITERATIONS,
    ASTEROID_RECYCLER_SHIP_KEY,
    AsteroidReadinessState,
    AsteroidReadState,
    advance_coordinate,
    candidate_limit,
    classify_dispatch_readiness,
    classify_read_state,
    movement_count,
    movement_margin_seconds,
    parse_asteroid_tooltip,
    predict_coordinate,
    server_wall_clock_to_utc,
)


FIXTURE = Path(__file__).parent / "fixtures" / "v2_asteroid_contract.html"


def _fixture_tooltip() -> str:
    html = FIXTURE.read_text(encoding="utf-8")
    match = re.search(r'<div id="sanitizedSquareInfo">(.*?)</div>\s*</body>', html, re.S)
    assert match
    return match.group(1)


def test_sanitized_fixture_locks_visible_galaxy_contract() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert 'id="galaxyHolder"' in html
    assert 'id="galaxyLoading"' in html
    assert 'src="https://static.example.invalid/img/planets/asteroid.png"' in html
    assert 'fleets.php?c1=2&amp;c2=23&amp;c3=8&amp;type=8' in html
    assert 'squareInfo(2, 23, 8)' in html
    assert "currentTime = new Date('August 06, 2026 20:57:38')" in html


def test_tooltip_parser_preserves_server_utc_plus_four_semantics() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    assert observation.coord == "2:23:8"
    assert observation.period_seconds == 61 * 60
    assert observation.last_move_at == datetime(2026, 8, 6, 16, 45, 8, tzinfo=timezone.utc)
    assert observation.next_move_at == datetime(2026, 8, 6, 17, 46, 8, tzinfo=timezone.utc)
    assert observation.observed_at == datetime(2026, 8, 6, 16, 57, 38, tzinfo=timezone.utc)
    assert observation.structurally_valid


def test_saved_tooltip_schedule_rolls_forward_after_announced_boundary() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 22, 50, 0),
    )
    assert observation.last_move_at == datetime(2026, 8, 6, 17, 46, 8, tzinfo=timezone.utc)
    assert observation.next_move_at == datetime(2026, 8, 6, 18, 47, 8, tzinfo=timezone.utc)


def test_tooltip_parser_rejects_partial_or_non_asteroid_evidence() -> None:
    with pytest.raises(ValueError):
        parse_asteroid_tooltip(
            "<div>Последнее перемещение 2026-08-06 20:45:08</div>",
            galaxy=2,
            system=23,
            position=8,
            observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
        )


def test_coordinate_contract_wraps_position_24_and_never_leaves_system_40() -> None:
    assert advance_coordinate(3, 38, 24, 1) == (3, 39, 1)
    assert advance_coordinate(3, 39, 24, 1) == (3, 40, 1)
    with pytest.raises(ValueError):
        advance_coordinate(3, ASTEROID_MAX_SYSTEM, 24, 1)
    with pytest.raises(ValueError):
        advance_coordinate(4, 1, 1, 0)


def test_movement_boundary_and_prediction_are_deterministic() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=24,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    just_before = observation.next_move_at - timedelta(seconds=1)
    just_after = observation.next_move_at + timedelta(seconds=1)
    assert movement_count(observation.next_move_at, observation.period_seconds, just_before) == 0
    assert movement_count(observation.next_move_at, observation.period_seconds, just_after) == 1
    target, shifts = predict_coordinate(observation, just_after)
    assert target == (2, 24, 1)
    assert shifts == 1
    assert movement_margin_seconds(observation.next_move_at, observation.period_seconds, just_after) == 1


def test_effective_legacy_plan_uses_margin_as_rejection_not_coordinate_shift() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    arrival = observation.next_move_at - timedelta(seconds=5)
    without_safety, _ = predict_coordinate(observation, arrival, safety_seconds=0)
    with_safety, _ = predict_coordinate(observation, arrival, safety_seconds=10)
    assert without_safety == (2, 23, 8)
    assert with_safety == (2, 23, 9)
    # The effective legacy _resolve_asteroid_plan uses safety_seconds=0 for the
    # coordinate and separately rejects a margin below the configured safety.
    assert movement_margin_seconds(observation.next_move_at, observation.period_seconds, arrival) == 5


def test_candidate_budget_contract_is_requested_plus_five_bounded_at_200() -> None:
    assert ASTEROID_CANDIDATE_RESERVE == 5
    assert ASTEROID_MAX_CANDIDATES == 200
    assert candidate_limit(10) == 15
    assert candidate_limit(1) == 6
    assert candidate_limit(200) == 200
    assert candidate_limit(500) == 200


def test_read_states_keep_unavailable_captcha_empty_and_ready_separate() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    assert classify_read_state(browser_available=False, captcha_present=False, observations=()) is AsteroidReadState.LIVE_UNAVAILABLE
    assert classify_read_state(browser_available=True, captcha_present=True, observations=()) is AsteroidReadState.CAPTCHA
    assert classify_read_state(browser_available=True, captcha_present=False, observations=()) is AsteroidReadState.NO_ASTEROIDS
    assert classify_read_state(browser_available=True, captcha_present=False, observations=(observation,)) is AsteroidReadState.READY


def test_dispatch_readiness_requires_valid_observation_recyclers_and_slot() -> None:
    observation = parse_asteroid_tooltip(
        _fixture_tooltip(),
        galaxy=2,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    assert classify_dispatch_readiness(
        browser_available=True,
        captcha_present=False,
        observation=observation,
        available_recyclers=25,
        requested_recyclers=5,
        free_fleet_slots=1,
    ) is AsteroidReadinessState.READY
    assert classify_dispatch_readiness(
        browser_available=True,
        captcha_present=False,
        observation=observation,
        available_recyclers=4,
        requested_recyclers=5,
        free_fleet_slots=1,
    ) is AsteroidReadinessState.CAPACITY_BLOCKED
    assert classify_dispatch_readiness(
        browser_available=True,
        captcha_present=False,
        observation=observation,
        available_recyclers=25,
        requested_recyclers=5,
        free_fleet_slots=0,
    ) is AsteroidReadinessState.CAPACITY_BLOCKED


def test_action_contract_constants_are_pinned_without_browser_implementation() -> None:
    assert ASTEROID_RECYCLER_SHIP_KEY == "ship_1_11"
    assert ASTEROID_MISSION_CODE == "8"
    assert ASTEROID_MISSION_NAME == "Добыча газа"
    assert ASTEROID_PLAN_MAX_ITERATIONS == 8
    assert server_wall_clock_to_utc(datetime(2026, 8, 6, 20, 0, 0)) == datetime(
        2026, 8, 6, 16, 0, 0, tzinfo=timezone.utc
    )
