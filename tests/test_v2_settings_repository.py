from pathlib import Path

import pytest

from v2.application.v2_settings import V2SettingError, V2SettingsRepository
from v2.persistence.database import V2Database


def test_defaults_and_roundtrip_are_typed(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        settings = V2SettingsRepository(db)
        assert settings.get("ui_reduce_motion") is False
        assert settings.get("ui_scale_percent") == 100
        assert settings.get("command_planet") == "2:5:6"
        assert settings.set("ui_reduce_motion", "true") is True
        assert settings.set("ui_scale_percent", "125") == 125
        assert settings.set("farm_home", " 3 : 39 : 11 ") == "3:39:11"

    with V2Database(path) as db:
        settings = V2SettingsRepository(db)
        assert settings.get("ui_reduce_motion") is True
        assert settings.get("ui_scale_percent") == 125
        assert settings.get("farm_home") == "3:39:11"


def test_invalid_or_unknown_settings_fail_before_write(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        settings = V2SettingsRepository(db)
        settings.set("cdp_port", 9333)
        before = db.read_all_settings_raw()
        with pytest.raises(V2SettingError):
            settings.set("cdp_port", 99999)
        with pytest.raises(V2SettingError):
            settings.set("password", "secret")
        with pytest.raises(V2SettingError):
            settings.set("command_planet", "bad")
        assert db.read_all_settings_raw() == before
        assert "password" not in db.read_all_settings_raw()


def test_repository_has_small_explicit_non_secret_allowlist() -> None:
    with V2Database(Path(":memory:")) as db:
        keys = set(V2SettingsRepository(db).keys())
        assert keys == {
            "ui_reduce_motion",
            "ui_scale_percent",
            "cdp_port",
            "farm_home",
            "command_planet",
            "farm_return_buffer_minutes",
        }
        assert not any(token in key.lower() for key in keys for token in ("password", "cookie", "token", "secret"))
