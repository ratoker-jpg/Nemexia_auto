from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "farm_wave_cooldown.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_default_buffer_is_five_minutes_and_user_configurable():
    assert "DEFAULT_RETURN_BUFFER_MINUTES = 5" in SOURCE
    assert 'text="Буфер после возврата, мин"' in SOURCE
    assert "from_=0" in SOURCE
    assert "MAX_RETURN_BUFFER_MINUTES = 60" in SOURCE
    assert 'farm_return_buffer_minutes' in SOURCE


def test_next_cycle_uses_latest_wave_return_plus_buffer():
    assert "latest = max(returns, default=None)" in SOURCE
    assert "deadline = last_return + timedelta(minutes=buffer)" in SOURCE
    assert 'farm_last_wave_return_at' in SOURCE
    assert 'farm_next_cycle_at' in SOURCE


def test_cooldown_blocks_new_scan_and_send_until_deadline():
    assert "if deadline is not None and deadline > now:" in SOURCE
    assert "return\n\n        if not self.auto_var.get() or self.busy" in SOURCE
    assert "return\n            self._farm_clear_deadline()" in SOURCE
    assert "original_auto_cycle(self)" in SOURCE


def test_only_auto_farm_wave_send_results_are_captured():
    assert "self._farm_wave_capture = True" in SOURCE
    assert "if getattr(self, \"_farm_wave_capture\", False):" in SOURCE
    assert "self._farm_wave_returns.append(returned)" in SOURCE
    assert 'text.startswith("Автофарм · отправлено")' in SOURCE


def test_existing_wave_after_upgrade_gets_same_buffer_rule():
    assert 'text.startswith("Автофарм · ждём возврата")' in SOURCE
    assert "self._farm_saved_deadline() is None" in SOURCE
    assert "_farm_attacks(list(self.active_flights), self.home())" in SOURCE


def test_installer_order_is_after_flight_classification():
    classification = ENTRY.index("install_farm_flight_classification_fix(BaseRaidManagerApp)")
    cooldown = ENTRY.index("install_farm_wave_cooldown(BaseRaidManagerApp)")
    motion = ENTRY.index("install_motion(BaseRaidManagerApp)")
    assert classification < cooldown < motion
