from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "fleet_capacity_settings_fallback.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_live_used_count_is_still_required() -> None:
    assert "#FleetsCount" in SOURCE
    assert 'raise BrowserAutomationError(\n            "Не удалось прочитать текущее число полётов' in SOURCE


def test_game_max_can_fall_back_to_configured_max_slots() -> None:
    assert 'configured_max = int(getattr(self, "_configured_fleet_max", 0) or 0)' in SOURCE
    assert "maximum = game_max if game_max > 0 else configured_max" in SOURCE
    assert "maximum <= 0" in SOURCE


def test_duplicate_or_stale_dom_nodes_are_handled() -> None:
    assert "querySelectorAll(selector)" in SOURCE
    assert "used = max(used_candidates)" in SOURCE
    assert "positive_max" in SOURCE
    assert "Пол[её]ты" in SOURCE


def test_current_setting_is_pushed_to_worker_before_sync_and_auto_send() -> None:
    assert "self.worker._configured_fleet_max = configured" in SOURCE
    assert "set_configured_max(self)" in SOURCE
    assert "original_farm_send_wave(self)" in SOURCE
    assert "original_sync_flights(self, silent=silent)" in SOURCE


def test_fallback_is_installed_after_capacity_presentation() -> None:
    presentation = ENTRY.index("install_fleet_capacity_presentation(BaseRaidManagerApp)")
    fallback = ENTRY.index(
        "install_fleet_capacity_settings_fallback(app_module.BrowserWorker, BaseRaidManagerApp)"
    )
    motion = ENTRY.index("install_motion(BaseRaidManagerApp)")
    assert presentation < fallback < motion
