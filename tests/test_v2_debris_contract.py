from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from v2.domain.asteroids import AsteroidObservationFact
from v2.domain.debris import (
    DEBRIS_CANONICAL_MARKER,
    DebrisReadState,
    classify_debris_read_state,
    debris_observation,
    has_debris_marker,
    parse_debris_square_info,
)


FIXTURE = Path(__file__).parent / "fixtures" / "v2_debris_contract.html"


def _template(name: str) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    start = text.index(f'<template id="{name}">')
    start = text.index(">", start) + 1
    end = text.index("</template>", start)
    return text[start:end]


def test_exact_square_info_marker_and_movement_provenance() -> None:
    evidence = parse_debris_square_info(
        _template("debris-ready"),
        galaxy=1,
        system=23,
        position=8,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    assert evidence.has_debris is True
    assert evidence.marker == DEBRIS_CANONICAL_MARKER
    assert evidence.coord == "1:23:8"
    assert isinstance(evidence.asteroid, AsteroidObservationFact)
    assert evidence.asteroid.period_seconds == 61 * 60
    assert evidence.asteroid.last_move_at == datetime(2026, 8, 6, 16, 45, 8, tzinfo=timezone.utc)
    assert evidence.asteroid.next_move_at == datetime(2026, 8, 6, 17, 46, 8, tzinfo=timezone.utc)
    fact = debris_observation(evidence)
    assert fact is not None
    assert fact.asteroid is evidence.asteroid
    assert fact.structurally_valid


def test_marker_rule_matches_effective_legacy_normalization() -> None:
    assert has_debris_marker("Этот астероид <b>содержит&nbsp;обломки</b>")
    assert not has_debris_marker("Информация об астероиде без указанного ресурса")


def test_valid_square_info_without_marker_is_proven_no_debris_candidate() -> None:
    evidence = parse_debris_square_info(
        _template("asteroid-without-debris"),
        galaxy=2,
        system=10,
        position=4,
        observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
    )
    assert evidence.has_debris is False
    assert debris_observation(evidence) is None
    assert classify_debris_read_state(
        browser_available=True,
        captcha_present=False,
        visible_asteroids=1,
        readable_square_info=1,
        debris_count=0,
    ) is DebrisReadState.NO_DEBRIS


def test_partial_square_info_is_not_no_debris() -> None:
    with pytest.raises(ValueError, match="movement timestamps"):
        parse_debris_square_info(
            _template("partial-square-info"),
            galaxy=3,
            system=39,
            position=11,
            observed_server_at=datetime(2026, 8, 6, 20, 57, 38),
        )
    assert classify_debris_read_state(
        browser_available=True,
        captcha_present=False,
        visible_asteroids=2,
        readable_square_info=1,
        debris_count=0,
    ) is DebrisReadState.PARTIAL_EVIDENCE


def test_captcha_and_live_unavailable_remain_distinct() -> None:
    assert classify_debris_read_state(
        browser_available=True,
        captcha_present=True,
        visible_asteroids=0,
        readable_square_info=0,
        debris_count=0,
    ) is DebrisReadState.CAPTCHA
    assert classify_debris_read_state(
        browser_available=False,
        captcha_present=False,
        visible_asteroids=0,
        readable_square_info=0,
        debris_count=0,
    ) is DebrisReadState.LIVE_UNAVAILABLE


def test_zero_visible_asteroids_is_no_debris_for_current_system_only() -> None:
    assert classify_debris_read_state(
        browser_available=True,
        captcha_present=False,
        visible_asteroids=0,
        readable_square_info=0,
        debris_count=0,
    ) is DebrisReadState.NO_DEBRIS


def test_evidence_counters_reject_impossible_partial_claims() -> None:
    with pytest.raises(ValueError, match="invalid debris evidence counters"):
        classify_debris_read_state(
            browser_available=True,
            captcha_present=False,
            visible_asteroids=1,
            readable_square_info=0,
            debris_count=1,
        )
