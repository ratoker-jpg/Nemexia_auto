from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "v2_navigation_contract.json"


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_effective_legacy_patch_order_keeps_bound_tab_then_background_navigation() -> None:
    entry = text("app_entry.py")
    bound_pos = entry.index("install_bound_tab_fix()")
    background_pos = entry.index("install_background_browser_fix()")
    import_app_pos = entry.index("import app as app_module")
    assert bound_pos < background_pos < import_app_pos


def test_bound_tab_contract_pins_page_object_but_not_account_or_planet_identity() -> None:
    source = text("bound_tab_fix.py")
    assert "_bound_nemexia_page" in source
    assert "GAME_HOST in str(page.url)" in source
    assert "page in _all_open_pages(worker)" in source
    assert "document.hasFocus()" in source
    assert "document.visibilityState === 'visible'" in source
    for absent_identity_proof in (
        "account_id",
        "player_id",
        "planet_id",
        "selected_planet_id",
    ):
        assert absent_identity_proof not in source


def test_effective_galaxy_ensure_can_switch_selected_planet_before_system_load() -> None:
    background = text("background_browser_fix.py")
    browser = text("browser.py")
    select_pos = background.index("await self._select_planet(page, home)")
    load_pos = background.index("await self._load_galaxy_system(page, galaxy, solar)")
    assert select_pos < load_pos
    assert "await page.goto(link" in browser
    assert "#planetsListHolder a" in browser
    assert "Игра оставила планету" in browser


def test_galaxy_system_refresh_is_a_remote_post_not_a_pure_local_dom_change() -> None:
    browser = text("browser.py")
    assert '"ajax_galaxy.php" in response.url' in browser
    assert 'response.request.method == "POST"' in browser
    assert "refreshGalaxy();" in browser
    assert "#c1" in browser and "#c2" in browser


def test_saved_evidence_contains_real_selected_planet_switch_surface() -> None:
    evidence = fixture()
    legacy = evidence["effective_legacy"]
    saved = evidence["saved_page_evidence"]
    assert legacy["planet_switch_route"] == "change_planet.php?id=<planet-id>"
    assert legacy["galaxy_ensure_calls_select_planet"] is True
    assert saved["current_planet_label"] == "[3:39:11]"
    assert saved["planet_switch_links_present"] is True
    assert saved["multiple_owned_planet_links_present"] is True


def test_current_v2_readers_are_attach_only_but_do_not_own_one_stable_bound_tab() -> None:
    read_backend = text("v2/infrastructure/cdp_read_backend.py")
    asteroid_reader = text("v2/infrastructure/cdp_asteroid_reader.py")
    assert "for context in browser.contexts for page in context.pages" in read_backend
    assert '"fleets.php" in item.url' in read_backend
    assert "for context in browser.contexts for page in context.pages" in asteroid_reader
    assert '"galaxy.php" in item.url' in asteroid_reader
    combined = read_backend + asteroid_reader
    for missing_ownership_primitive in (
        "_bound_nemexia_page",
        "bound_page_token",
        "account_identity_token",
        "selected_planet_identity_token",
    ):
        assert missing_ownership_primitive not in combined


def test_v2_67_decision_is_no_navigation_boundary_until_identity_semantics_are_proven() -> None:
    evidence = fixture()
    assert evidence["decision"] == "NO_NAVIGATION_BOUNDARY"
    v2 = evidence["v2_current_boundary"]
    assert v2["attach_only"] is True
    assert v2["stable_bound_page_token"] is False
    assert v2["account_identity_token"] is False
    assert v2["selected_planet_identity_token"] is False
    assert len(evidence["unproven_semantics"]) >= 4
    forbidden = set(evidence["forbidden_after_audit"])
    assert {
        "page.goto for V2 navigation",
        "refreshGalaxy from V2",
        "ajax_galaxy.php navigation POST from V2",
        "change_planet.php from V2",
        "automatic 3x40 traversal",
        "Rest Mode navigation loops",
        "background navigation",
    }.issubset(forbidden)


def test_v2_67_research_files_do_not_add_navigation_runtime() -> None:
    tree_files = (
        "v2/infrastructure/cdp_read_backend.py",
        "v2/infrastructure/cdp_asteroid_reader.py",
        "v2/infrastructure/cdp_debris_reader.py",
    )
    combined = "\n".join(text(path) for path in tree_files)
    for forbidden in (
        ".goto(",
        "refreshGalaxy(",
        "ajax_galaxy.php",
        "change_planet.php",
        "new_page(",
    ):
        assert forbidden not in combined
