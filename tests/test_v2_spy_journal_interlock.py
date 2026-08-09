from __future__ import annotations

from pathlib import Path

import pytest

from v2.application.automatic_recon import AutomaticReconService
from v2.application.spy_actions import SpyRequestCommand, SpyRequestRejected
from v2.application.spy_journal import SpyRequestBlocked, SpyRequestCoordinator
from v2.persistence.automatic_recon_journal import AutomaticReconJournalRepository
from v2.persistence.database import V2Database


class ManualSpyService:
    enabled = True

    def __init__(self) -> None:
        self.prepare_calls = 0

    def prepare(self, command):
        self.prepare_calls += 1
        raise AssertionError("manual spy preparation must not run across unresolved AUTO-07")


def begin_auto(journal: AutomaticReconJournalRepository) -> None:
    journal.begin(
        request_id="auto-pending",
        fleet_id="152272",
        source_coord="3:39:11",
        target_coord="2:22:19",
        account_fingerprint="acct",
        planet_id="planet-1",
        baseline_keys=(),
    )


def test_unresolved_automatic_recon_blocks_manual_exact_fleet_before_prepare(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    automatic = AutomaticReconJournalRepository(database)
    begin_auto(automatic)
    service = ManualSpyService()
    manual = SpyRequestCoordinator(service, database)
    with pytest.raises(SpyRequestBlocked, match="automatic recon"):
        manual.request(SpyRequestCommand("152273"), request_id="manual-1")
    assert service.prepare_calls == 0
    database.close()


def test_unresolved_manual_spy_blocks_automatic_recon_before_browser_work(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    automatic = AutomaticReconJournalRepository(database)
    database.begin_spy_action(
        request_id="manual-pending",
        fleet_id="152272",
        source="3:39:11",
        target="2:22:19",
    )
    service = AutomaticReconService(object(), object(), automatic, enabled=True)
    with pytest.raises(SpyRequestRejected, match="manual spy request"):
        service.run(request_id="auto-1")
    assert automatic.read("auto-1") is None
    database.close()
