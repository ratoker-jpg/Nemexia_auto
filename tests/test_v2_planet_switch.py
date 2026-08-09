from __future__ import annotations

from pathlib import Path

import pytest

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.persistence.database import V2Database, V2DatabaseError
from v2.persistence.navigation_journal import NavigationJournalRepository


def _observation(selected_id: str) -> NavigationObservation:
    selected_coord = "3:39:11" if selected_id == "101" else "3:39:8"
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url="https://game.ares.nemexia.com/fleets.php",
        page_count=1,
        game_page_count=1,
        planets=(
            PlanetDomFact("101", "3:39:11", "HOME", selected_id == "101"),
            PlanetDomFact("202", "3:39:8", "GAS", selected_id == "202"),
        ),
        trigger_coord=selected_coord,
    )
    return NavigationObservation("runtime-page:42", identity)


class _SwitchBackend:
    def __init__(self, *, fail: bool = False, reconcile_after_failure: bool = False) -> None:
        self.current = _observation("101")
        self.fail = fail
        self.reconcile_after_failure = reconcile_after_failure
        self.switch_calls = 0
        self.closed = False

    def observe(self) -> NavigationObservation:
        return self.current

    def switch_planet(self, *, planet_id: str, expected_coord: str, expected_account_fingerprint: str) -> NavigationObservation:
        self.switch_calls += 1
        assert planet_id == "202"
        assert expected_coord == "3:39:8"
        assert expected_account_fingerprint == self.current.identity.account.ownership_fingerprint
        if self.fail:
            if self.reconcile_after_failure:
                self.current = _observation("202")
            raise RuntimeError("navigation transport lost")
        self.current = _observation("202")
        return self.current

    def close(self) -> None:
        self.closed = True


def _coordinator(tmp_path: Path, backend: _SwitchBackend) -> tuple[V2Database, NavigationCoordinator]:
    database = V2Database(tmp_path / "v2.sqlite3")
    return database, NavigationCoordinator(backend, NavigationJournalRepository(database))


def test_switch_planet_attempts_remote_navigation_exactly_once_and_verifies_identity(tmp_path: Path) -> None:
    backend = _SwitchBackend()
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.switch_planet(request_id="switch-1", planet_id="202")
        assert backend.switch_calls == 1
        assert record.status == "verified"
        assert record.before["planet_id"] == "101"
        assert record.intent["planet_id"] == "202"
        assert record.after is not None
        assert record.after["planet_id"] == "202"
        assert record.before["page_token"] == record.after["page_token"]
        assert record.before["account_fingerprint"] == record.after["account_fingerprint"]
    finally:
        coordinator.close()
        database.close()


def test_same_planet_is_verified_without_remote_attempt(tmp_path: Path) -> None:
    backend = _SwitchBackend()
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.switch_planet(request_id="same-1", planet_id="101")
        assert record.status == "verified"
        assert backend.switch_calls == 0
        assert "no remote mutation" in record.detail
    finally:
        coordinator.close()
        database.close()


def test_unowned_planet_fails_safe_without_remote_attempt(tmp_path: Path) -> None:
    backend = _SwitchBackend()
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.switch_planet(request_id="bad-1", planet_id="999")
        assert record.status == "failed_safe"
        assert backend.switch_calls == 0
    finally:
        coordinator.close()
        database.close()


def test_uncertain_remote_effect_becomes_ambiguous_and_is_never_retried(tmp_path: Path) -> None:
    backend = _SwitchBackend(fail=True)
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.switch_planet(request_id="uncertain-1", planet_id="202")
        assert record.status == "ambiguous"
        assert backend.switch_calls == 1
        with pytest.raises(V2DatabaseError, match="already exists"):
            coordinator.switch_planet(request_id="uncertain-1", planet_id="202")
        assert backend.switch_calls == 1
    finally:
        coordinator.close()
        database.close()


def test_backend_error_can_be_reconciled_only_from_read_after_evidence(tmp_path: Path) -> None:
    backend = _SwitchBackend(fail=True, reconcile_after_failure=True)
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.switch_planet(request_id="reconcile-1", planet_id="202")
        assert record.status == "verified"
        assert backend.switch_calls == 1
        assert "read reconciliation" in record.detail
    finally:
        coordinator.close()
        database.close()


def test_auto04_is_the_only_v2_planet_navigation_path() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_navigation_backend.py").read_text(encoding="utf-8")
    coordinator = (root / "v2" / "application" / "navigation.py").read_text(encoding="utf-8")

    assert source.count(".goto(") == 1
    assert "#planetsListHolder a" in source
    assert "change_planet.php" in source
    assert "searchParams.get('id')" in source
    assert "expected_account_fingerprint" in source
    assert "automatic retry forbidden" in coordinator
    assert "_switch_verified" in coordinator
    assert "current.planet_id == target.planet_id" in coordinator
    assert "current.coord == target.coord" in coordinator
    assert "refreshGalaxy(" not in source
    assert "processSpy(" not in source
    assert "SendFleet(" not in source
