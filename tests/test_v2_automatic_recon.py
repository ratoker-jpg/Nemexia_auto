from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from v2.application.automatic_recon import (
    AutomaticReconAmbiguous,
    AutomaticReconMutationError,
    AutomaticReconService,
    ProcessableSpyFleet,
    select_new_exact_report,
    select_processable_spy_fleet,
)
from v2.application.spy_actions import SpyRequestRejected
from v2.domain.recon import SpyReportFact
from v2.persistence.automatic_recon_journal import (
    AutomaticReconConflictError,
    AutomaticReconJournalRepository,
)
from v2.persistence.database import V2Database


SOURCE = "3:39:11"
TARGET = "2:22:19"
FLEET = ProcessableSpyFleet("152272", SOURCE, TARGET, 0)


def report(report_id: str, *, target: str = TARGET, when: datetime | None = None) -> SpyReportFact:
    return SpyReportFact(
        report_id=report_id,
        target=target,
        reported_at=when or datetime.now(timezone.utc),
        metal=100,
        minerals=200,
        gas=300,
    )


class FakeNavigation:
    def __init__(self) -> None:
        self.kind = "fleets"
        self.page_token = "runtime-page:1"

    def observe(self):
        planet = SimpleNamespace(planet_id="planet-1", coord=SOURCE)
        account = SimpleNamespace(ownership_fingerprint="acct:ares:planet-1")
        identity = SimpleNamespace(current_planet=planet, account=account)
        page = SimpleNamespace(page_kind=self.kind)
        return SimpleNamespace(page_token=self.page_token, identity=identity, page=page)


class FakeReadiness:
    def __init__(self, navigation: FakeNavigation) -> None:
        self.navigation = navigation
        self.calls: list[str] = []

    def ensure_fleets(self, *, planet_coord: str | None = None):
        self.calls.append("fleets")
        self.navigation.kind = "fleets"

    def ensure_messages(self, *, planet_coord: str | None = None):
        self.calls.append("messages")
        self.navigation.kind = "options"


class FakeBrowser:
    def __init__(
        self,
        *,
        process_error: Exception | None = None,
        fresh_report_after_call: int = 2,
    ) -> None:
        self.process_error = process_error
        self.fresh_report_after_call = max(2, int(fresh_report_after_call))
        self.discover_calls = 0
        self.report_calls = 0
        self.process_calls = 0

    def discover_spy_fleets(self, **_kwargs):
        self.discover_calls += 1
        return (FLEET,)

    def read_spy_reports(self, **_kwargs):
        self.report_calls += 1
        old = report(
            "old-report",
            when=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        if self.report_calls < self.fresh_report_after_call:
            return (old,)
        fresh = report(
            "new-report",
            when=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
        return (old, fresh)

    def process_spy_once(self, **_kwargs):
        self.process_calls += 1
        if self.process_error is not None:
            raise self.process_error


def build_service(tmp_path: Path, browser: FakeBrowser):
    database = V2Database(tmp_path / "v2.sqlite3")
    journal = AutomaticReconJournalRepository(database)
    navigation = FakeNavigation()
    service = AutomaticReconService(browser, navigation, journal, enabled=True)
    service.readiness = FakeReadiness(navigation)
    return database, journal, service


def test_processable_fleet_selection_requires_proven_ready_timer_and_is_deterministic() -> None:
    chosen = select_processable_spy_fleet(
        (
            ProcessableSpyFleet("200", SOURCE, "1:1:1", 5),
            ProcessableSpyFleet("101", SOURCE, "1:1:2", None),
            ProcessableSpyFleet("99", SOURCE, "1:1:3", 0),
            ProcessableSpyFleet("100", SOURCE, "1:1:4", 0),
        )
    )
    assert chosen is not None
    assert chosen.fleet_id == "99"
    assert select_processable_spy_fleet((ProcessableSpyFleet("1", SOURCE, TARGET, 1),)) is None


def test_exact_report_verification_requires_new_id_target_and_fresh_time() -> None:
    requested = datetime.now(timezone.utc)
    old = report("old", when=requested - timedelta(minutes=5))
    wrong_target = report("new-wrong", target="1:1:1", when=requested)
    fresh = report("new-right", when=requested + timedelta(seconds=1))
    chosen = select_new_exact_report(
        (old, wrong_target, fresh),
        before_ids=frozenset({"old"}),
        target=TARGET,
        requested_at=requested,
    )
    assert chosen is fresh


def test_persistent_journal_blocks_unresolved_and_reopens_after_safe_terminal(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "journal.sqlite3")
    journal = AutomaticReconJournalRepository(database)
    first = journal.begin(
        request_id="auto-1",
        fleet_id="152272",
        source_coord=SOURCE,
        target_coord=TARGET,
        account_fingerprint="acct",
        planet_id="planet-1",
        baseline_keys=("old",),
    )
    assert first.status == "pending"
    with pytest.raises(AutomaticReconConflictError):
        journal.begin(
            request_id="auto-2",
            fleet_id="152273",
            source_coord=SOURCE,
            target_coord="2:22:20",
            account_fingerprint="acct",
            planet_id="planet-1",
            baseline_keys=(),
        )
    terminal = journal.finish(
        "auto-1",
        status="failed_safe",
        after_keys=None,
        detail="preflight failed before mutation",
    )
    assert terminal.status == "failed_safe"
    assert journal.unresolved() == ()
    database.close()


def test_success_uses_exactly_one_process_spy_and_persists_verified_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("v2.application.automatic_recon.time.sleep", lambda _seconds: None)
    browser = FakeBrowser()
    database, journal, service = build_service(tmp_path, browser)
    result = service.run(request_id="auto-success")
    assert result.verified is True
    assert result.fleet_id == "152272"
    assert result.report_id == "new-report"
    assert browser.process_calls == 1
    assert browser.discover_calls == 2
    record = journal.read("auto-success")
    assert record is not None
    assert record.status == "verified"
    assert record.baseline_keys == ("old-report",)
    assert record.after_keys == ("new-report", "old-report")
    database.close()


def test_verification_polls_for_delayed_report_without_repeating_process_spy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("v2.application.automatic_recon.time.sleep", lambda _seconds: None)
    browser = FakeBrowser(fresh_report_after_call=4)
    database, journal, service = build_service(tmp_path, browser)
    result = service.run(request_id="auto-delayed-report")
    assert result.verified is True
    assert result.report_id == "new-report"
    assert browser.report_calls == 4
    assert browser.process_calls == 1
    record = journal.read("auto-delayed-report")
    assert record is not None and record.status == "verified"
    database.close()


def test_post_attempt_error_is_ambiguous_and_second_request_cannot_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("v2.application.automatic_recon.time.sleep", lambda _seconds: None)
    browser = FakeBrowser(
        process_error=AutomaticReconMutationError(
            "remote effect unknown",
            remote_attempted=True,
        )
    )
    database, journal, service = build_service(tmp_path, browser)
    with pytest.raises(AutomaticReconAmbiguous):
        service.run(request_id="auto-ambiguous")
    assert browser.process_calls == 1
    record = journal.read("auto-ambiguous")
    assert record is not None and record.status == "ambiguous"
    with pytest.raises(SpyRequestRejected, match="unresolved"):
        service.run(request_id="auto-no-retry")
    assert browser.process_calls == 1
    database.close()


def test_pre_attempt_error_is_failed_safe_not_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("v2.application.automatic_recon.time.sleep", lambda _seconds: None)
    browser = FakeBrowser(
        process_error=AutomaticReconMutationError(
            "row disappeared before processSpy",
            remote_attempted=False,
        )
    )
    database, journal, service = build_service(tmp_path, browser)
    with pytest.raises(SpyRequestRejected):
        service.run(request_id="auto-failed-safe")
    record = journal.read("auto-failed-safe")
    assert record is not None and record.status == "failed_safe"
    assert journal.unresolved() == ()
    database.close()
