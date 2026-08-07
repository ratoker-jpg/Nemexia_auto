from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "resource_queue_modes.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_two_explicit_queue_modes_exist() -> None:
    assert "def generate_queue_by_metal" in SOURCE
    assert "def generate_queue_by_minerals" in SOURCE
    assert 'generate_queue_by_resource(self, "metal")' in SOURCE
    assert 'generate_queue_by_resource(self, "minerals")' in SOURCE


def test_metal_mode_keeps_metal_threshold() -> None:
    assert 'resource == "metal"' in SOURCE
    assert "value < minimum_metal" in SOURCE
    assert 'values["min_metal_for_queue"]' in SOURCE


def test_minerals_mode_does_not_reuse_metal_threshold() -> None:
    mineral_block = SOURCE.split('elif resource == "minerals":', 1)[1].split("else:", 1)[0]
    assert "target.minerals" in mineral_block
    assert "minimum_metal" not in mineral_block


def test_common_safety_filters_are_preserved() -> None:
    for token in (
        "not target.enabled",
        "target.blacklisted",
        "target.coord in active",
        "target.last_spy_at is None",
    ):
        assert token in SOURCE


def test_ui_replaces_ambiguous_build_button() -> None:
    assert 'button.configure(text="Собрать по металлу"' in SOURCE
    assert '"Собрать по минералам"' in SOURCE


def test_legacy_generate_queue_defaults_to_metal() -> None:
    assert "Keep legacy callers" in SOURCE
    assert "app_class.generate_queue = generate_queue" in SOURCE


def test_priority_column_tracks_selected_resource() -> None:
    assert 'tree.heading("score", text=f"Приоритет · {label}")' in SOURCE
    assert "target.metal if mode == \"metal\" else target.minerals" in SOURCE


def test_install_order_keeps_row_numbering_after_resource_render() -> None:
    assert ENTRY.index("install_resource_queue_modes(BaseRaidManagerApp)") < ENTRY.index(
        "install_queue_row_numbering(BaseRaidManagerApp)"
    )
