from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "farm_flight_classification_fix.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_farm_waits_only_normal_attack_from_configured_home() -> None:
    assert '_mission(flight) == "атака"' in SOURCE
    assert '_coord(getattr(flight, "source", "")) == source' in SOURCE
    assert 'farm_attacks = _farm_attacks(all_flights, home)' in SOURCE
    assert 'len(farm_attacks)' in SOURCE


def test_recycling_does_not_block_cycle_but_still_uses_capacity() -> None:
    assert 'if farm_attacks:' in SOURCE
    assert 'slot_flights = _slot_flights(all_flights)' in SOURCE
    assert 'free = max(0, max_slots - len(slot_before))' in SOURCE
    assert 'переработ' not in SOURCE.casefold() or 'Other missions, including recycling, still occupy a slot.' in SOURCE


def test_sun_attack_is_incoming_and_not_our_slot() -> None:
    assert '_mission(flight) != "атака солнца"' in SOURCE
    assert 'Атака Солнца' in SOURCE


def test_hotfix_installs_after_auto_farm_layer() -> None:
    assert 'from farm_flight_classification_fix import install_farm_flight_classification_fix' in ENTRY
    farm = ENTRY.index('install_resource_farm_auto(BaseRaidManagerApp)')
    classification = ENTRY.index('install_farm_flight_classification_fix(BaseRaidManagerApp)')
    assert farm < classification
