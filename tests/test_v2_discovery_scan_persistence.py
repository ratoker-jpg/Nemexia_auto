from pathlib import Path

import pytest

from v2.persistence.database import V2Database
from v2.persistence.discovery_scan import (
    DISCOVERY_SYSTEM_COUNT,
    DiscoveryScanConflictError,
    DiscoveryScanRepository,
)


def begin(repo: DiscoveryScanRepository, scan_id: str = "scan-1"):
    return repo.begin(
        scan_id=scan_id,
        account_fingerprint="acct",
        planet_id="planet-1",
        planet_coord="3:39:11",
    )


def test_cursor_persists_across_restart_and_incomplete_scan_is_not_last_completed(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    database = V2Database(path)
    repo = DiscoveryScanRepository(database)
    begin(repo)
    scan = repo.record_system(
        scan_id="scan-1",
        sequence_index=0,
        galaxy=1,
        solar=40,
        asteroid_count=2,
        debris_count=1,
        observed_at="2026-08-09T16:00:00+00:00",
    )
    assert scan.cursor_index == 1
    assert repo.last_completed() is None
    database.close()

    reopened = V2Database(path)
    repo2 = DiscoveryScanRepository(reopened)
    restored = repo2.read("scan-1")
    assert restored is not None
    assert restored.status == "running"
    assert restored.cursor_index == 1
    assert repo2.systems("scan-1")[0].solar == 40
    assert repo2.last_completed() is None
    reopened.close()


def test_complete_requires_exactly_120_committed_system_rows(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    repo = DiscoveryScanRepository(database)
    begin(repo)
    with pytest.raises(DiscoveryScanConflictError, match="incomplete"):
        repo.complete("scan-1")

    for index in range(DISCOVERY_SYSTEM_COUNT):
        galaxy = index // 40 + 1
        solar = 40 - (index % 40)
        repo.record_system(
            scan_id="scan-1",
            sequence_index=index,
            galaxy=galaxy,
            solar=solar,
            asteroid_count=0,
            debris_count=0,
            observed_at=f"2026-08-09T16:{index % 60:02d}:00+00:00",
        )
    completed = repo.complete("scan-1")
    assert completed.done is True
    assert completed.cursor_index == 120
    assert len(repo.systems("scan-1")) == 120
    assert repo.last_completed() == completed
    database.close()


def test_stopped_scan_can_resume_but_ambiguous_scan_cannot_auto_resume(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    repo = DiscoveryScanRepository(database)
    begin(repo, "stopped")
    stopped = repo.finish_safe("stopped", status="stopped", detail="operator")
    assert stopped.status == "stopped"
    assert repo.resume("stopped").status == "running"
    repo.finish_safe("stopped", status="ambiguous", detail="unknown remote effect")
    with pytest.raises(DiscoveryScanConflictError, match="Only stopped/failed_safe"):
        repo.resume("stopped")
    database.close()


def test_resume_rejects_competing_running_scan_and_preserves_single_active_scan(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    repo = DiscoveryScanRepository(database)

    begin(repo, "scan-A")
    repo.finish_safe("scan-A", status="stopped", detail="operator")
    begin(repo, "scan-B")

    with pytest.raises(DiscoveryScanConflictError, match="scan-B \(running\)"):
        repo.resume("scan-A")

    scan_a = repo.read("scan-A")
    scan_b = repo.read("scan-B")
    assert scan_a is not None and scan_a.status == "stopped"
    assert scan_b is not None and scan_b.status == "running"
    unresolved = repo.unresolved()
    assert [(row.scan_id, row.status) for row in unresolved] == [("scan-B", "running")]
    database.close()
