from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "command_planet_exclusion.py").read_text(encoding="utf-8")


def test_existing_history_is_hidden_not_deleted() -> None:
    assert "DELETE FROM history" not in SOURCE
    assert "SELECT * FROM history" in SOURCE
    assert "Database.list_history = list_history" in SOURCE


def test_new_command_planet_history_is_rejected_before_persist() -> None:
    assert "if is_command_planet_result(result):" in SOURCE
    assert "return None" in SOURCE
