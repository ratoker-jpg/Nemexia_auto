from __future__ import annotations

from pathlib import Path

import pytest

from v2.application.asteroid_autorenew_context import AsteroidAutorenewApplicationContext
from v2.application.automation_authority import (
    ASTEROID_AUTORENEW_OWNER,
    AUTOFARM_OWNER,
    AutomationAuthority,
    AutomationAuthorityError,
)
from v2.persistence.asteroid_autorenew import AsteroidAutorenewRepository
from v2.persistence.database import V2Database, V2DatabaseError
from v2.persistence.discovery_scan import DiscoveryScanRepository


ROOT = Path(__file__).resolve().parents[1]


def _arm(repo: AsteroidAutorenewRepository, session_id: str) -> None:
    repo.arm(
        session_id=session_id,
        source_planet_id="101",
        source_coord="3:39:8",
        account_fingerprint="acct",
        recycler_count=5,
        max_flights=15,
        safety_seconds=10,
        buffer_minutes=5,
    )


def test_crash_gap_adopts_orphaned_autorenew_scan_before_restart_disarm(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    database = V2Database(path)
    autorenew = AsteroidAutorenewRepository(database)
    discovery = DiscoveryScanRepository(database)
    _arm(autorenew, "session-crash-gap")

    # Reproduce the exact review gap: AUTO-10 commits a running row, then the
    # process dies before scheduler.transition(active_scan_id=scan.scan_id).
    orphan = discovery.begin(
        scan_id="autorenew-scan:session-crash-gap:orphan",
        account_fingerprint="acct",
        planet_id="101",
        planet_coord="3:39:8",
    )
    assert autorenew.read().active_scan_id is None
    database.close()

    reopened = V2Database(path)
    recovered_repo = AsteroidAutorenewRepository(reopened)
    recovered = recovered_repo.disarm_on_startup()

    assert recovered.armed is False
    assert recovered.status == "disarmed_restart"
    assert recovered.active_scan_id == orphan.scan_id
    assert orphan.scan_id in recovered.detail
    assert DiscoveryScanRepository(reopened).read(orphan.scan_id).status == "running"

    with pytest.raises(V2DatabaseError, match=orphan.scan_id):
        _arm(recovered_repo, "session-after-crash-gap")
    assert recovered_repo.read().active_scan_id == orphan.scan_id
    reopened.close()


def test_shared_authority_allows_only_one_automatic_mutation_owner() -> None:
    authority = AutomationAuthority()
    assert authority.owner() is None
    assert authority.acquire(AUTOFARM_OWNER) == AUTOFARM_OWNER
    assert authority.owner() == AUTOFARM_OWNER

    with pytest.raises(AutomationAuthorityError, match="autofarm"):
        authority.acquire(ASTEROID_AUTORENEW_OWNER)

    authority.release(AUTOFARM_OWNER)
    assert authority.acquire(ASTEROID_AUTORENEW_OWNER) == ASTEROID_AUTORENEW_OWNER
    with pytest.raises(AutomationAuthorityError, match="asteroid_autorenew"):
        authority.ensure_available(AUTOFARM_OWNER)
    authority.release(ASTEROID_AUTORENEW_OWNER)
    assert authority.owner() is None


def test_asteroid_start_is_rejected_before_service_when_autofarm_owns_authority() -> None:
    calls: list[str] = []

    class Service:
        def start(self, **_kwargs):
            calls.append("service-start")
            raise AssertionError("service/browser work must not run")

    context = object.__new__(AsteroidAutorenewApplicationContext)
    context._asteroid_autorenew = Service()
    context._automation_authority = AutomationAuthority()
    context._automation_authority.acquire(AUTOFARM_OWNER)

    with pytest.raises(AutomationAuthorityError, match="autofarm"):
        context.start_asteroid_autorenew(source="3:39:8", start_immediately=False)
    assert calls == []
    assert context.automation_cycle_owner() == AUTOFARM_OWNER


def test_farm_wave_is_rejected_before_parent_dispatch_when_asteroid_owns_authority() -> None:
    context = object.__new__(AsteroidAutorenewApplicationContext)
    context._automation_authority = AutomationAuthority()
    context._automation_authority.acquire(ASTEROID_AUTORENEW_OWNER)

    with pytest.raises(AutomationAuthorityError, match="asteroid_autorenew"):
        context.run_farm_wave(ship_count=25, max_targets=15)
    assert context.automation_cycle_owner() == ASTEROID_AUTORENEW_OWNER


def test_existing_farm_surface_acquires_and_releases_shared_authority() -> None:
    wrapper = (ROOT / "v2" / "ui" / "pages" / "farm_authority.py").read_text(encoding="utf-8")
    main_window = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "class AuthorityFarmPage(FarmPage)" in wrapper
    assert "ensure_automation_cycle_available" in wrapper
    assert "acquire_automation_cycle" in wrapper
    assert "release_automation_cycle" in wrapper
    assert "AUTOFARM_OWNER" in wrapper
    assert wrapper.index("_acquire_farm_authority()") < wrapper.index("super().start_cycle()")
    assert "def _disarm" in wrapper and "self._release_farm_authority()" in wrapper
    assert "AuthorityFarmPage(self.context, self)" in main_window

    for forbidden in ("playwright", "#FleetsCount", "SendFleetButton", "refreshGalaxy"):
        assert forbidden not in wrapper
