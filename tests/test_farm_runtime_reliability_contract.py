from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "farm_runtime_reliability.py").read_text(encoding="utf-8")
PRESENTATION = (ROOT / "fleet_capacity_presentation.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")
SNAPSHOT = (
    ROOT / "saved_pages" / "2026-08-08_08-54-11-072" / "page.html"
).read_text(encoding="utf-8")


def test_saved_fleets_page_exposes_authoritative_capacity_counter() -> None:
    assert 'id="FleetsCount">20<' in SNAPSHOT
    assert 'id="MaxFleets">22<' in SNAPSHOT


def test_sender_reads_game_counter_instead_of_counting_filtered_rows() -> None:
    assert "#FleetsCount" in RUNTIME
    assert "#MaxFleets" in RUNTIME
    assert 'capacity_before = await self.worker.read_fleet_capacity()' in RUNTIME
    assert 'effective_max - int(capacity_before["used"])' in RUNTIME
    assert "configured_max - len(slot_before)" not in RUNTIME
    assert "max_slots - len(slot_before)" not in RUNTIME


def test_mission_type_does_not_define_capacity_but_attack_type_still_defines_timing() -> None:
    assert "_slot_flights(all_before)" in RUNTIME
    assert "_farm_attacks(all_before, home)" in RUNTIME
    assert "_farm_attacks(all_after, home)" in RUNTIME
    assert "read_fleet_capacity" in RUNTIME


def test_sync_and_dashboard_show_game_capacity_but_return_timer_is_our_attack_only() -> None:
    assert "Подключено · полёты: {used}/{maximum}" in PRESENTATION
    assert 'self.card_slots_var.set(f"{int(used)} / {int(maximum)}")' in PRESENTATION
    assert "attacks = _farm_attacks(list(self.active_flights), self.home())" in PRESENTATION
    assert "next_return = min(" in PRESENTATION


def test_auto_farm_controls_have_dedicated_full_width_card_and_truthful_button() -> None:
    assert 'text="АВТОФАРМ 500K"' in RUNTIME
    assert 'text="Буфер после возврата, мин"' in RUNTIME
    assert "wraplength=max(320" in RUNTIME
    assert 'text="Остановить автофарм" if enabled else "Запустить автофарм 500k"' in RUNTIME
    assert 'BUTTON_SPECS["danger" if enabled else "success"]' in RUNTIME


def test_install_order_preserves_capacity_then_cooldown_then_ui() -> None:
    classification = ENTRY.index("install_farm_flight_classification_fix(BaseRaidManagerApp)")
    capacity = ENTRY.index("install_farm_capacity_fix(app_module.BrowserWorker, BaseRaidManagerApp)")
    cooldown = ENTRY.index("install_farm_wave_cooldown(BaseRaidManagerApp)")
    ui = ENTRY.index("install_farm_ui_fix(BaseRaidManagerApp)")
    presentation = ENTRY.index("install_fleet_capacity_presentation(BaseRaidManagerApp)")
    motion = ENTRY.index("install_motion(BaseRaidManagerApp)")
    assert classification < capacity < cooldown < ui < presentation < motion
