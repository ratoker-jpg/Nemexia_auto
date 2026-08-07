from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "command_planet_exclusion.py").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_command_planet_coordinate_is_exact() -> None:
    assert 'COMMAND_PLANET_COORD = "2:5:6"' in SOURCE


def test_both_source_and_target_are_excluded() -> None:
    assert 'getattr(flight, "source", "")' in SOURCE
    assert 'getattr(flight, "target", "")' in SOURCE
    assert 'result.get("source")' in SOURCE
    assert 'result.get("target")' in SOURCE


def test_active_flights_are_filtered_centrally() -> None:
    assert "original_sync_all_flights = BrowserWorker.sync_all_flights" in SOURCE
    assert "BrowserWorker.sync_all_flights = sync_all_flights" in SOURCE
    assert "not is_command_planet_flight(flight)" in SOURCE


def test_history_and_raid_calculations_exclude_command_planet() -> None:
    assert "Database.add_history = add_history" in SOURCE
    assert "Database.list_history = list_history" in SOURCE
    assert "Database.last_raid_map = last_raid_map" in SOURCE
    assert "COALESCE(REPLACE(source, ' ', ''), '') <> ?" in SOURCE
    assert "REPLACE(target, ' ', '') <> ?" in SOURCE


def test_filter_is_installed_before_higher_level_flight_features() -> None:
    all_slots = BOOTSTRAP.index("install_all_flight_slot_fix(BaseRaidManagerApp)")
    exclusion = BOOTSTRAP.index("install_command_planet_exclusion()")
    farm = BOOTSTRAP.index("install_farm_flight_classification_fix(BaseRaidManagerApp)")
    assert all_slots < exclusion < farm
