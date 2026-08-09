from __future__ import annotations

from pathlib import Path

import pytest

from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.asteroid_journal import AsteroidJournalRepository
from v2.persistence.backup import create_v2_backup
from v2.persistence.database import V2Database, V2_SCHEMA_VERSION
from v2.persistence.debris_candidates import DebrisObservationRepository
from v2.release_lifecycle import ReleaseLifecycleError, V2ProductionSession
from v2.runtime_paths import RuntimePaths, ensure_runtime_paths


NOW = "2026-08-09T10:30:00+00:00"
LAST_MOVE = "2026-08-09T10:00:00+00:00"
NEXT_MOVE = "2026-08-09T11:00:00+00:00"


def _paths(tmp_path: Path) -> RuntimePaths:
    root = tmp_path / "NemexiaRaidManagerV2"
    return ensure_runtime_paths(RuntimePaths(
        root=root,
        database=root / "nemexia.sqlite3",
        browser_profile=root / "browser-profile",
        logs=root / "logs",
        screenshots=root / "screenshots",
        backups=root / "backups",
    ))


class _Context:
    def __init__(self, database: V2Database) -> None:
        self._v2_database = database
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self._v2_database.close()
            self.closed = True


def _factory(paths: RuntimePaths) -> _Context:
    return _Context(V2Database(paths.database))


def test_production_session_clean_start_creates_startup_and_shutdown_backups(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    assert not paths.database.exists()

    session = V2ProductionSession(paths, _factory)
    with session as context:
        database = context._v2_database
        assert database.schema_version() == V2_SCHEMA_VERSION == 9
        assert database.integrity_check() == "ok"
        database.write_setting_raw("cdp_port", "9444")
        assert session.startup_backup is not None and session.startup_backup.is_file()

    assert context.closed is True
    assert session.shutdown_backup is not None and session.shutdown_backup.is_file()
    assert session.startup_backup != session.shutdown_backup
    assert len(list(paths.backups.glob("nemexia_v2_*.sqlite3"))) == 2

    with V2Database(session.startup_backup) as startup:
        assert startup.integrity_check() == "ok"
        assert startup.schema_version() == 9
        assert startup.read_setting_raw("cdp_port") is None
    with V2Database(session.shutdown_backup) as shutdown:
        assert shutdown.integrity_check() == "ok"
        assert shutdown.read_setting_raw("cdp_port") == "9444"


def test_startup_backup_failure_closes_context_before_user_operation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    created: list[_Context] = []

    def factory(runtime_paths: RuntimePaths) -> _Context:
        context = _factory(runtime_paths)
        created.append(context)
        return context

    def fail_backup(_database: V2Database, _directory: Path) -> Path:
        raise OSError("backup disk unavailable")

    with pytest.raises(ReleaseLifecycleError, match="startup backup failed"):
        with V2ProductionSession(paths, factory, backup_factory=fail_backup):
            raise AssertionError("user operation must not start after backup failure")

    assert len(created) == 1
    assert created[0].closed is True


def test_shutdown_backup_failure_is_visible_and_still_closes_context(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    calls = 0
    created: list[_Context] = []

    def factory(runtime_paths: RuntimePaths) -> _Context:
        context = _factory(runtime_paths)
        created.append(context)
        return context

    def backup(database: V2Database, directory: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("shutdown backup disk unavailable")
        return create_v2_backup(database, directory)

    with pytest.raises(ReleaseLifecycleError, match="shutdown backup failed"):
        with V2ProductionSession(paths, factory, backup_factory=backup):
            created[0]._v2_database.write_setting_raw("cdp_port", "9555")

    assert calls == 2
    assert created[0].closed is True


def test_shutdown_backup_error_does_not_mask_existing_application_error(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    calls = 0
    created: list[_Context] = []

    def factory(runtime_paths: RuntimePaths) -> _Context:
        context = _factory(runtime_paths)
        created.append(context)
        return context

    def backup(database: V2Database, directory: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("secondary shutdown backup failure")
        return create_v2_backup(database, directory)

    with pytest.raises(RuntimeError, match="primary application failure"):
        with V2ProductionSession(paths, factory, backup_factory=backup):
            raise RuntimeError("primary application failure")

    assert calls == 2
    assert created[0].closed is True


def test_restart_preserves_v2_owned_state_and_unresolved_journals(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    with V2ProductionSession(paths, _factory) as first:
        db = first._v2_database
        db.write_setting_raw("cdp_port", "9666")
        db.begin_raid_action(
            request_id="raid-pending",
            source="3:39:11",
            target="2:22:19",
            player="restart",
            ship_count=25,
        )
        db.import_raid_queue_rows([{
            "legacy_id": 501,
            "position": 1,
            "state": "ambiguous",
            "coord": "2:22:19",
            "player": "restart",
            "metal": 500000,
            "minerals": 600000,
            "gas": 700000,
            "last_spy_at": NOW,
            "enabled": True,
            "blacklisted": False,
        }])
        db.begin_spy_action(
            request_id="spy-pending",
            fleet_id="152272",
            source="3:39:11",
            target="1:21:17",
        )
        db.import_recon_target_rows([{
            "coord": "1:21:17",
            "player": "restart-recon",
            "enabled": True,
        }])
        db.insert_recon_report_rows([{
            "report_id": "restart-report",
            "target": "1:21:17",
            "report_at": NOW,
            "energy": 9000,
            "metal": 800000,
            "minerals": 700000,
            "gas": 600000,
            "source": "restart:test",
        }])
        AsteroidJournalRepository(db).begin(
            request_id="asteroid-pending",
            source="3:39:11",
            observation_coord="3:39:20",
            observation_last_move_at=LAST_MOVE,
            observation_next_move_at=NEXT_MOVE,
            observation_period_seconds=3600,
            observation_observed_at=NOW,
            target="3:39:21",
            recycler_count=5,
            safety_seconds=10,
            prepared_at=NOW,
            one_way_seconds=30,
            round_trip_seconds=60,
            shifts=0,
            gas_needed=100,
        )
        AsteroidObservationRepository(db).insert([{
            "galaxy": 3,
            "system": 39,
            "position": 20,
            "last_move_at": LAST_MOVE,
            "next_move_at": NEXT_MOVE,
            "period_seconds": 3600,
            "observed_at": NOW,
            "source": "restart:test",
        }])
        DebrisObservationRepository(db).insert([{
            "galaxy": 3,
            "system": 39,
            "position": 20,
            "last_move_at": LAST_MOVE,
            "next_move_at": NEXT_MOVE,
            "period_seconds": 3600,
            "observed_at": NOW,
            "evidence_source": "restart:test",
            "marker": "Этот астероид содержит обломки",
        }])

    with V2ProductionSession(paths, _factory) as restarted:
        db = restarted._v2_database
        assert db.integrity_check() == "ok"
        assert db.schema_version() == 9
        assert db.read_setting_raw("cdp_port") == "9666"
        assert db.read_raid_action("raid-pending")["status"] == "pending"
        queue = db.list_raid_queue_rows()
        assert len(queue) == 1 and queue[0]["state"] == "ambiguous"
        assert db.read_spy_action("spy-pending")["status"] == "pending"
        assert db.list_recon_target_rows()[0]["coord"] == "1:21:17"
        assert db.list_recon_report_rows()[0]["report_id"] == "restart-report"
        assert AsteroidJournalRepository(db).read("asteroid-pending")["status"] == "pending"
        assert AsteroidObservationRepository(db).list()[0]["position"] == 20
        assert DebrisObservationRepository(db).list()[0]["marker"] == "Этот астероид содержит обломки"

    backups = list(paths.backups.glob("nemexia_v2_*.sqlite3"))
    assert len(backups) == 4
    for backup_path in backups:
        with V2Database(backup_path) as backup:
            assert backup.integrity_check() == "ok"
            assert backup.schema_version() == 9
