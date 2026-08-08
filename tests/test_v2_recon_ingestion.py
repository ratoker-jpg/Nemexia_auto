from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from v2.application.read_store import ReadOnlyStore
from v2.application.recon_repository import V2ReconRepository
from v2.domain.recon import SpyReportFact
from v2.persistence.database import V2Database


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _report(
    report_id: str | None,
    target: str,
    at: datetime | None,
    *,
    metal: int | None = 480_000,
    minerals: int | None = 500_000,
) -> SpyReportFact:
    return SpyReportFact(
        report_id=report_id,
        target=target,
        reported_at=at,
        energy=7000,
        metal=metal,
        minerals=minerals,
        gas=12_000,
        source="browser:TabAdministrative",
    )


def test_ingest_rejects_partial_and_stale_and_is_idempotent(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2ReconRepository(db)
        result = repo.ingest_reports(
            (
                _report("fresh-1", "2:22:19", NOW - timedelta(minutes=5)),
                _report(None, "2:22:20", NOW - timedelta(minutes=1)),
                _report("undated", "2:22:21", None),
                _report("stale", "2:22:22", NOW - timedelta(hours=25)),
            ),
            now=NOW,
        )
        assert (result.inserted, result.duplicates, result.rejected_partial, result.rejected_stale) == (1, 0, 2, 1)

        again = repo.ingest_reports((_report("fresh-1", "2:22:19", NOW - timedelta(minutes=5)),), now=NOW)
        assert (again.inserted, again.duplicates) == (0, 1)

        rows = repo.list_recon()
        assert len(rows) == 1
        assert rows[0].report_id == "fresh-1"
        assert rows[0].target_coord == "2:22:19"
        assert rows[0].minerals == 500_000


def test_latest_target_projection_is_deterministic_by_report_time_then_id(tmp_path: Path) -> None:
    target = "2:22:19"
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2ReconRepository(db)
        repo.ingest_reports(
            (
                _report("z-new", target, NOW - timedelta(minutes=1), minerals=510_000),
                _report("old", target, NOW - timedelta(minutes=3), minerals=900_000),
                _report("a-new", target, NOW - timedelta(minutes=1), minerals=520_000),
            ),
            now=NOW,
        )
        row = next(item for item in repo.list_targets() if item.coord == target)
        assert row.latest_report_id == "z-new"
        assert row.minerals == 510_000

        # Re-ingesting the same set in another order cannot change the projection.
        repo.ingest_reports(
            (
                _report("a-new", target, NOW - timedelta(minutes=1), minerals=520_000),
                _report("old", target, NOW - timedelta(minutes=3), minerals=900_000),
                _report("z-new", target, NOW - timedelta(minutes=1), minerals=510_000),
            ),
            now=NOW,
        )
        same = next(item for item in repo.list_targets() if item.coord == target)
        assert same.latest_report_id == "z-new"
        assert same.minerals == 510_000


def _legacy_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE targets (
            coord TEXT PRIMARY KEY, player TEXT, energy INTEGER, g INTEGER, s INTEGER, p INTEGER,
            enabled INTEGER, blacklisted INTEGER, notes TEXT, metal INTEGER, minerals INTEGER,
            resource_gas INTEGER, last_spy_at TEXT, raid_count INTEGER, last_raid_at TEXT,
            last_return_at TEXT
        );
        CREATE TABLE history (
            id INTEGER PRIMARY KEY, source TEXT, target TEXT, player TEXT, ship_count INTEGER,
            sent_at TEXT, arrival_at TEXT, return_at TEXT, status TEXT, error TEXT
        );
        CREATE TABLE queue (id INTEGER PRIMARY KEY, coord TEXT, position INTEGER, state TEXT);
        INSERT INTO targets VALUES(
            '3:1:2','Seed Player',7000,3,1,2,0,1,'legacy note',100,200,300,
            '2026-08-08T10:00:00+00:00',0,NULL,NULL
        );
        """)


def test_legacy_target_seed_is_read_only_and_never_overwrites_v2_metadata(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.sqlite3"
    _legacy_db(legacy_path)
    before = legacy_path.read_bytes()
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2ReconRepository(db)
        with ReadOnlyStore(legacy_path) as legacy:
            assert repo.import_legacy_targets(legacy) == 1
            assert repo.import_legacy_targets(legacy) == 0

        assert db.import_recon_target_rows(({
            "coord": "3:1:2", "player": "Changed", "enabled": True,
            "blacklisted": False, "notes": "overwrite attempt",
        },)) == 0
        target = repo.list_targets()[0]
        assert target.player == "Seed Player"
        assert target.enabled is False
        assert target.blacklisted is True
        assert target.notes == "legacy note"
    assert legacy_path.read_bytes() == before


def test_ingest_creates_v2_target_for_new_coordinate_without_legacy_row(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        repo = V2ReconRepository(db)
        result = repo.ingest_reports((_report("new-target", "4:9:7", NOW),), now=NOW)
        assert result.inserted == 1
        target = repo.list_targets()[0]
        assert target.coord == "4:9:7"
        assert target.enabled is True and target.blacklisted is False
        assert target.latest_report_id == "new-target"
