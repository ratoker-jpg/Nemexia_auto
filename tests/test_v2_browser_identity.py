from __future__ import annotations

from pathlib import Path

import pytest

from v2.application.browser_identity import (
    BrowserIdentityError,
    PlanetDomFact,
    build_browser_identity,
    ownership_fingerprint,
)


def _facts(*, reverse: bool = False) -> tuple[PlanetDomFact, ...]:
    rows = (
        PlanetDomFact("101", "3:39:11", "HOME", True),
        PlanetDomFact("202", "3:39:8", "GAS", False),
    )
    return tuple(reversed(rows)) if reverse else rows


def test_identity_keeps_internal_id_name_coord_selected_and_account_evidence() -> None:
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222/",
        page_url="https://game.ares.nemexia.com/fleets.php",
        page_count=3,
        game_page_count=1,
        planets=_facts(),
        trigger_coord="3:39:11",
    )

    assert identity.session.endpoint == "http://127.0.0.1:9222"
    assert identity.session.server_host == "game.ares.nemexia.com"
    assert identity.account.planet_ids == ("101", "202")
    assert identity.account.planet_coords == ("3:39:11", "3:39:8")
    assert len(identity.account.ownership_fingerprint) == 64

    home = identity.by_id("101")
    assert home is not None
    assert home.coord == "3:39:11"
    assert home.display_name == "HOME"
    assert home.selected is True
    assert home.selected_proof == "#planetsListHolder li.active + #planetSwitch"
    assert home.account_fingerprint == identity.account.ownership_fingerprint
    assert identity.current_planet == home


def test_account_fingerprint_is_stable_for_same_owned_planet_set() -> None:
    first = ownership_fingerprint("game.ares.nemexia.com", _facts())
    second = ownership_fingerprint("GAME.ARES.NEMEXIA.COM", _facts(reverse=True))
    assert first == second


def test_selected_planet_evidence_must_agree() -> None:
    with pytest.raises(BrowserIdentityError, match="disagrees"):
        build_browser_identity(
            endpoint="http://127.0.0.1:9222",
            page_url="https://game.ares.nemexia.com/fleets.php",
            page_count=1,
            game_page_count=1,
            planets=_facts(),
            trigger_coord="3:39:8",
        )


def test_planet_identity_rejects_duplicate_or_unowned_evidence() -> None:
    duplicate = (
        PlanetDomFact("101", "3:39:11", "HOME", True),
        PlanetDomFact("101", "3:39:8", "OTHER", False),
    )
    with pytest.raises(BrowserIdentityError, match="Duplicate internal planet ID"):
        build_browser_identity(
            endpoint="http://127.0.0.1:9222",
            page_url="https://game.ares.nemexia.com/fleets.php",
            page_count=1,
            game_page_count=1,
            planets=duplicate,
            trigger_coord="3:39:11",
        )

    with pytest.raises(BrowserIdentityError, match="outside the owned planet list"):
        build_browser_identity(
            endpoint="http://127.0.0.1:9222",
            page_url="https://game.ares.nemexia.com/fleets.php",
            page_count=1,
            game_page_count=1,
            planets=_facts(),
            trigger_coord="1:1:1",
        )


def test_auto02_cdp_identity_reader_is_still_strictly_read_only() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_account_reader.py").read_text(encoding="utf-8")

    assert "#planetSwitch .trigger big" in source
    assert "#planetsListHolder a" in source
    assert "change_planet.php" in source
    assert "searchParams.get('id')" in source
    assert "selected_by_list" in source
    assert "build_browser_identity" in source

    for forbidden in (
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "bring_to_front(",
        "refreshGalaxy(",
        "processSpy(",
        "SendFleet(",
    ):
        assert forbidden not in source
