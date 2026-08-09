from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.asteroid_journal import AsteroidJournalRepository
from v2.persistence.backup import create_v2_backup
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION
from v2.persistence.debris_candidates import DebrisObservationRepository


NOW = "2026-08-09T07:00:00+00:00"
LAST_MOVE = "2026-08-09T06:00:00+00:00"
NEXT_MOVE = "2026-08-09T08:00:00+00:00"
MARKER = "Этот астероид содержит обломки"


def _debris_row() -> dict[str, object]:
    return {
        "galaxy": 1,
        "system": 39,
        "position": 24,
        "last_move_at": LAST_MOVE,
        "next_move_at": NEXT_MOVE,
        "period_seconds": 3600,
        "observed_at": NOW,
        "evidence_source": "galaxy.squareInfo",
        "marker": MARKER,
    }


def _downgrade_metadata_to_v8(path: Path, *, keep_debris_table: bool) -> None:
    with sqlite3.connect(path) as conn:
        if not keep_debris_table:
            conn.execute("DROP TABLE debris_observations")
        conn.execute("DELETE FROM schema_migrations WHERE version=9")
        conn.execute("PRAGMA user_version=8")


def test_clean_database_is_schema9_and_installs_debris_without_repository(tmp_path: Path) -> None:
    path = tmp_path / "clean.sqlite3"
    with V2Database(path) as db:
        assert db.schema_version() == V2_SCHEMA_VERSION == 9
        assert "debris_observations" in db.table_names()
        versions = db._require_conn().execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [int(row[0]) for row in versions] == list(range(1, 10))


def test_schema8_without_debris_table_migrates_to_9_and_preserves_old_data(tmp_path: Path) -> None:
    path = tmp_path / "schema8-without-debris.sqlite3"
    with V2Database(path) as db:
        db.write_setting_raw("cdp_port", "9555")
    _downgrade_metadata_to_v8(path, keep_debris_table=False)

    with V2Database(path) as migrated:
        assert migrated.schema_version() == 9
        assert "debris_observations" in migrated.table_names()
        assert migrated.read_setting_raw("cdp_port") == "9555"
        assert migrated._require_conn().execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=9"
        ).fetchone()[0] == 1
        assert migrated.integrity_check() == "ok"


def test_schema8_with_feature_local_debris_migrates_idempotently_without_row_loss(tmp_path: Path) -> None:
    path = tmp_path / "schema8-with-feature-debris.sqlite3"
    with V2Database(path) as db:
        repo = DebrisObservationRepository(db)
        assert repo.insert([_debris_row()]) == 1
        original = repo.list()
        assert len(original) == 1
    _downgrade_metadata_to_v8(path, keep_debris_table=True)

    with V2Database(path) as migrated:
        repo = DebrisObservationRepository(migrated)
        rows = repo.list()
        assert migrated.schema_version() == 9
        assert len(rows) == 1
        assert rows[0]["id"] == original[0]["id"]
        assert rows[0]["marker"] == MARKER
        assert repo.insert([_debris_row()]) == 0
        assert len(repo.list()) == 1
        assert migrated._require_conn().execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=9"
        ).fetchone()[0] == 1


def test_schema9_backup_restore_preserves_debris_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    with V2Database(source) as db:
        repo = DebrisObservationRepository(db)
        assert repo.insert([_debris_row()]) == 1
        backup = create_v2_backup(
            db,
            tmp_path / "backups",
            now=datetime(2026, 8, 9, 7, 30, tzinfo=timezone.utc),
        )

    with V2Database(backup) as restored:
        rows = DebrisObservationRepository(restored).list()
        assert restored.schema_version() == 9
        assert len(rows) == 1
        assert rows[0]["marker"] == MARKER
        assert rows[0]["evidence_source"] == "galaxy.squareInfo"
        assert restored.integrity_check() == "ok"


def test_schema8_to_9_preserves_every_preexisting_v2_table(tmp_path: Path) -> None:
    path = tmp_path / "schema8-full-state.sqlite3"
    with V2Database(path) as db:
        db.write_setting_raw("cdp_port", "9666")
        db.begin_raid_action(
            request_id="raid-preserve",
            source="3:39:11",
            target="2:22:19",
            player="preserve",
            ship_count=25,
        )
        db.import_raid_queue_rows([
            {
                "legacy_id": 77,
                "position": 1,
                "state": "queued",
                "coord": "2:22:19",
                "player": "preserve",
                "metal": 123,
                "minerals": 456,
                "gas": 789,
                "last_spy_at": NOW,
                "enabled": True,
                "blacklisted": False,
            }
        ])
        db.begin_spy_action(
            request_id="spy-preserve",
            fleet_id="31415",
            source="3:39:11",
            target="1:21:17",
        )
        db.import_recon_target_rows([
            {"coord": "1:21:17", "player": "recon-preserve", "enabled": True}
        ])
        db.insert_recon_report_rows([
            {
                "report_id": "report-preserve",
                "target": "1:21:17",
                "report_at": NOW,
                "energy": 1,
                "metal": 2,
                "minerals": 3,
                "gas": 4,
                "source": "messages",
            }
        ])
        AsteroidJournalRepository(db).begin(
            request_id="asteroid-preserve",
            source="3:39:11",
            observation_coord="1:10:5",
            observation_last_move_at=LAST_MOVE,
            observation_next_move_at=NEXT_MOVE,
            observation_period_seconds=3600,
            observation_observed_at=NOW,
            target="1:10:6",
            recycler_count=25,
            safety_seconds=10,
            prepared_at=NOW,
            one_way_seconds=30,
            round_trip_seconds=60,
            shifts=0,
            gas_needed=100,
        )
        AsteroidObservationRepository(db).insert([
            {
                "galaxy": 1,
                "system": 10,
                "position": 5,
                "last_move_at": LAST_MOVE,
                "next_move_at": NEXT_MOVE,
                "period_seconds": 3600,
                "observed_at": NOW,
                "source": "galaxy.squareInfo",
            }
        ])
    _downgrade_metadata_to_v8(path, keep_debris_table=False)

    with V2Database(path) as migrated:
        assert migrated.schema_version() == 9
        assert migrated.read_setting_raw("cdp_port") == "9666"
        assert migrated.read_raid_action("raid-preserve")["target"] == "2:22:19"
        assert migrated.list_raid_queue_rows()[0]["imported_legacy_id"] == 77
        assert migrated.read_spy_action("spy-preserve")["fleet_id"] == "31415"
        assert migrated.list_recon_target_rows()[0]["coord"] == "1:21:17"
        assert migrated.list_recon_report_rows()[0]["report_id"] == "report-preserve"
        assert AsteroidJournalRepository(migrated).read("asteroid-preserve")["target"] == "1:10:6"
        asteroid_rows = AsteroidObservationRepository(migrated).list()
        assert len(asteroid_rows) == 1
        assert asteroid_rows[0]["system"] == 10
        assert "debris_observations" in migrated.table_names()
        assert migrated.integrity_check() == "ok"
