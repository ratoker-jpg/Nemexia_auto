from __future__ import annotations

import sqlite3
from pathlib import Path

from v2.application.legacy_settings_import import LegacySettingsImporter
from v2.application.read_store import ReadOnlyStore
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database


LEGACY_SCHEMA = """
CREATE TABLE targets (coord TEXT PRIMARY KEY);
CREATE TABLE history (id INTEGER PRIMARY KEY);
CREATE TABLE queue (id INTEGER PRIMARY KEY);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def create_legacy(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?)",
            (
                ("port", "9333"),
                ("home_g", "3"), ("home_s", "39"), ("home_p", "11"),
                ("farm_return_buffer_minutes", "7"),
                ("some_secret_token", "must-not-copy"),
            ),
        )


def test_import_copies_only_allowlisted_values_and_never_mutates_legacy(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite3"
    create_legacy(legacy)
    before = legacy.read_bytes()

    with ReadOnlyStore(legacy) as source, V2Database(tmp_path / "v2.sqlite3") as db:
        target = V2SettingsRepository(db)
        result = LegacySettingsImporter(source, target).import_missing()
        assert set(result.imported) == {"cdp_port", "farm_home", "farm_return_buffer_minutes"}
        assert result.rejected == ()
        assert target.get("cdp_port") == 9333
        assert target.get("farm_home") == "3:39:11"
        assert target.get("farm_return_buffer_minutes") == 7
        raw = db.read_all_settings_raw()
        assert "some_secret_token" not in raw
        assert "must-not-copy" not in raw.values()

    assert legacy.read_bytes() == before


def test_import_is_idempotent_and_does_not_overwrite_explicit_v2_choice(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite3"
    create_legacy(legacy)
    before = legacy.read_bytes()

    with ReadOnlyStore(legacy) as source, V2Database(tmp_path / "v2.sqlite3") as db:
        target = V2SettingsRepository(db)
        target.set("cdp_port", 9444)
        importer = LegacySettingsImporter(source, target)
        first = importer.import_missing()
        second = importer.import_missing()
        assert "cdp_port" in first.skipped_existing
        assert target.get("cdp_port") == 9444
        assert set(second.skipped_existing) == {"cdp_port", "farm_home", "farm_return_buffer_minutes"}
        assert second.imported == ()

    assert legacy.read_bytes() == before


def test_invalid_legacy_value_is_rejected_without_default_write(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite3"
    create_legacy(legacy)
    with sqlite3.connect(legacy) as conn:
        conn.execute("UPDATE settings SET value='99999' WHERE key='port'")
    before = legacy.read_bytes()

    with ReadOnlyStore(legacy) as source, V2Database(tmp_path / "v2.sqlite3") as db:
        target = V2SettingsRepository(db)
        result = LegacySettingsImporter(source, target).import_missing()
        assert "cdp_port" in result.rejected
        assert db.read_setting_raw("cdp_port") is None
        assert target.get("cdp_port") == 9222

    assert legacy.read_bytes() == before
