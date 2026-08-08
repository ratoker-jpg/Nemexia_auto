from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.backup import create_v2_backup
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION


def test_backup_contains_committed_settings_and_is_restoreable(tmp_path: Path) -> None:
    source_path = tmp_path / "v2.sqlite3"
    backups = tmp_path / "backups"
    with V2Database(source_path) as db:
        settings = V2SettingsRepository(db)
        settings.set_many({"cdp_port": 9444, "farm_return_buffer_minutes": 9})
        backup = create_v2_backup(
            db,
            backups,
            now=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc),
        )
        assert backup.is_file()

    with V2Database(backup) as restored:
        settings = V2SettingsRepository(restored)
        assert restored.integrity_check() == "ok"
        assert restored.schema_version() == V2_SCHEMA_VERSION
        assert "raid_actions" in restored.table_names()
        assert settings.get("cdp_port") == 9444
        assert settings.get("farm_return_buffer_minutes") == 9


def test_backup_retention_keeps_newest_requested_count(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        for offset in range(4):
            create_v2_backup(
                db,
                tmp_path / "backups",
                keep=2,
                now=datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc) + timedelta(minutes=offset),
            )
    backups = sorted((tmp_path / "backups").glob("nemexia_v2_*.sqlite3"))
    assert len(backups) == 2
    assert backups[-1].name.endswith("110300Z.sqlite3")
