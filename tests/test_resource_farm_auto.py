from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "resource_farm_auto.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_source_compiles() -> None:
    compile(SOURCE, "resource_farm_auto.py", "exec")


def test_farm_threshold_is_500k_minerals() -> None:
    assert "FARM_MIN_MINERALS = 500_000" in SOURCE
    assert "target.minerals" in SOURCE
    assert ">= FARM_MIN_MINERALS" in SOURCE


def test_cycle_refreshes_then_sends_then_waits_for_returns() -> None:
    assert "sync_flights()" in SOURCE
    assert "collect_spy_reports()" in SOURCE
    assert "delete_spy_messages" in SOURCE
    assert "request_all_spy_reports()" in SOURCE
    assert "send_raid(target, ship_count, home)" in SOURCE
    assert "ждём возврата" in SOURCE


def test_captcha_is_stop_only_not_automated() -> None:
    assert "captcha_present()" in SOURCE
    assert "CaptchaRequiredError" in SOURCE
    assert "Автофарм остановлен: CAPTCHA" in SOURCE
    assert "g-recaptcha" not in SOURCE
    assert "recaptcha-anchor" not in SOURCE
    assert "iframe" not in SOURCE


def test_legacy_auto_does_not_silently_migrate() -> None:
    assert 'self.db.set_setting("auto_enabled", False)' in SOURCE
    assert "app_class._auto_cycle = auto_cycle" in SOURCE
    assert "Автоматически отправлять план" in SOURCE
    assert "Автофарм 500k" in SOURCE


def test_bootstrap_installs_farm_after_queue_behaviors() -> None:
    resource = ENTRY.index("install_resource_queue_modes(BaseRaidManagerApp)")
    numbering = ENTRY.index("install_queue_row_numbering(BaseRaidManagerApp)")
    farm = ENTRY.index("install_resource_farm_auto(BaseRaidManagerApp)")
    motion = ENTRY.index("install_motion(BaseRaidManagerApp)")
    assert resource < numbering < farm < motion
