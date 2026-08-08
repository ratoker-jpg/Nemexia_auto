from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from v2.domain.asteroids import AsteroidObservationFact, parse_asteroid_tooltip


DEBRIS_CANONICAL_MARKER = "Этот астероид содержит обломки"
DEBRIS_MARKER_FRAGMENT = "содержит обломки"


class DebrisReadState(str, Enum):
    """Typed result of a current-system debris evidence read."""

    LIVE_UNAVAILABLE = "live_unavailable"
    CAPTCHA = "captcha"
    NO_DEBRIS = "no_debris"
    PARTIAL_EVIDENCE = "partial_evidence"
    READY = "ready"


@dataclass(frozen=True)
class DebrisSquareInfoEvidence:
    """One readable asteroid squareInfo response plus its debris marker fact."""

    asteroid: AsteroidObservationFact
    has_debris: bool
    marker: str = DEBRIS_CANONICAL_MARKER

    @property
    def coord(self) -> str:
        return self.asteroid.coord


@dataclass(frozen=True)
class DebrisObservationFact:
    """A debris-bearing asteroid with the authoritative movement provenance."""

    asteroid: AsteroidObservationFact
    marker: str = DEBRIS_CANONICAL_MARKER
    source: str = "galaxy.squareInfo"

    @property
    def coord(self) -> str:
        return self.asteroid.coord

    @property
    def structurally_valid(self) -> bool:
        return self.asteroid.structurally_valid and self.marker == DEBRIS_CANONICAL_MARKER


def normalize_square_info_text(value: str) -> str:
    """Normalize squareInfo HTML exactly as the effective legacy debris detector does."""

    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html_module.unescape(text).replace("\xa0", " ").casefold().split())


def has_debris_marker(value: str) -> bool:
    """Preserve the accepted legacy marker rule while recording its canonical sentence."""

    return DEBRIS_MARKER_FRAGMENT in normalize_square_info_text(value)


def parse_debris_square_info(
    tooltip_html: str,
    *,
    galaxy: int,
    system: int,
    position: int,
    observed_server_at: datetime,
) -> DebrisSquareInfoEvidence:
    """Parse movement provenance first, then classify the debris marker.

    A malformed/partial squareInfo response raises ``ValueError`` instead of being
    silently downgraded to ``no_debris``. The current-system reader can therefore
    keep partial/unreadable evidence distinct from a proven empty result.
    """

    asteroid = parse_asteroid_tooltip(
        tooltip_html,
        galaxy=galaxy,
        system=system,
        position=position,
        observed_server_at=observed_server_at,
    )
    return DebrisSquareInfoEvidence(asteroid=asteroid, has_debris=has_debris_marker(tooltip_html))


def debris_observation(evidence: DebrisSquareInfoEvidence) -> DebrisObservationFact | None:
    if not evidence.has_debris:
        return None
    return DebrisObservationFact(asteroid=evidence.asteroid)


def classify_debris_read_state(
    *,
    browser_available: bool,
    captcha_present: bool,
    visible_asteroids: int,
    readable_square_info: int,
    debris_count: int,
) -> DebrisReadState:
    """Classify one already-open system without inventing full-scan semantics."""

    visible = int(visible_asteroids)
    readable = int(readable_square_info)
    debris = int(debris_count)
    if visible < 0 or readable < 0 or debris < 0 or readable > visible or debris > readable:
        raise ValueError("invalid debris evidence counters")
    if captcha_present:
        return DebrisReadState.CAPTCHA
    if not browser_available:
        return DebrisReadState.LIVE_UNAVAILABLE
    if readable < visible:
        return DebrisReadState.PARTIAL_EVIDENCE
    if debris == 0:
        return DebrisReadState.NO_DEBRIS
    return DebrisReadState.READY
