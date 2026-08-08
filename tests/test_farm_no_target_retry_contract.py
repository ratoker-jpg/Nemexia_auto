from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "farm_no_target_retry.py").read_text(encoding="utf-8")
ENTRY = (ROOT / "app_entry.py").read_text(encoding="utf-8")


def test_no_target_retry_is_fixed_at_25_minutes() -> None:
    assert "NO_TARGET_RETRY_MINUTES = 25" in SOURCE
    assert "time.monotonic() + NO_TARGET_RETRY_MINUTES * 60" in SOURCE
    assert "повтор через {NO_TARGET_RETRY_MINUTES} мин" in SOURCE


def test_only_empty_500k_scan_status_triggers_retry_override() -> None:
    assert 'prefix = "Автофарм · целей с 500 000 минералов нет"' in SOURCE
    assert "if str(text).startswith(prefix):" in SOURCE


def test_settings_explain_legacy_repeat_value_no_longer_controls_autofarm() -> None:
    assert '"Повторный рейд (старый параметр)"' in SOURCE
    assert '"автофарм 500k: при 0 подходящих целей пауза всегда 25 минут"' in SOURCE


def test_retry_layer_is_installed_immediately_after_resource_farm() -> None:
    resource = ENTRY.index("install_resource_farm_auto(BaseRaidManagerApp)")
    retry = ENTRY.index("install_farm_no_target_retry(BaseRaidManagerApp)")
    classification = ENTRY.index("install_farm_flight_classification_fix(BaseRaidManagerApp)")
    assert resource < retry < classification
