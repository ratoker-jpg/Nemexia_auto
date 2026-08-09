from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.debris_repository import V2DebrisRepository
from v2.application.discovery_scan import (
    DISCOVERY_SEQUENCE,
    ControlledDiscoveryScan,
    DiscoverySystemEvidence,
)
from v2.application.navigation import NavigationObservation, NavigationPageState
from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.database import V2Database
from v2.persistence.discovery_scan import DiscoveryScanRepository


SOURCE = "3:39:11"


def observation(*, galaxy: int = 3, solar: int = 39) -> NavigationObservation:
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url=f"https://game.ares.nemexia.com/galaxy.php?galaxy={galaxy}&solar={solar}",
        page_count=1,
        game_page_count=1,
        planets=(PlanetDomFact("101", SOURCE, "HOME", True),),
        trigger_coord=SOURCE,
    )
    return NavigationObservation(
        "runtime-page:scan",
        identity,
        NavigationPageState(
            page_kind="galaxy",
            galaxy_ready=True,
            galaxy=galaxy,
            solar=solar,
        ),
    )


class FakeNavigation:
    def __init__(self) -> None:
        self.current = observation()
        self.calls: list[tuple[int, int]] = []
        self.unresolved_rows: tuple[object, ...] = ()
        self.next_status = "verified"

    def observe(self):
        return self.current

    def unresolved(self):
        return self.unresolved_rows

    def navigate_galaxy_system(self, *, request_id: str, galaxy: int, solar: int):
        self.calls.append((galaxy, solar))
        if self.next_status == "verified":
            self.current = observation(galaxy=galaxy, solar=solar)
        return SimpleNamespace(status=self.next_status, detail=self.next_status)


class FakeBrowser:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.visible = 0
        self.readable = 0
        self.error: Exception | None = None

    def read_discovery_system(self, *, expected_galaxy: int, expected_solar: int, **_kwargs):
        self.calls.append((expected_galaxy, expected_solar))
        if self.error is not None:
            raise self.error
        return DiscoverySystemEvidence(
            galaxy=expected_galaxy,
            solar=expected_solar,
            observed_server_at=datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc),
            visible_asteroids=self.visible,
            readable_square_info=self.readable,
            asteroids=(),
            debris=(),
        )


def service(tmp_path: Path):
    database = V2Database(tmp_path / "v2.sqlite3")
    navigation = FakeNavigation()
    browser = FakeBrowser()
    scan = ControlledDiscoveryScan(
        browser=browser,
        navigation=navigation,
        repository=DiscoveryScanRepository(database),
        asteroid_storage=AsteroidObservationRepository(database),
        debris_repository=V2DebrisRepository(database),
    )
    return database, navigation, browser, scan


def test_sequence_is_exact_legacy_equivalent_3x40_order() -> None:
    assert len(DISCOVERY_SEQUENCE) == 120
    assert DISCOVERY_SEQUENCE[:3] == ((1, 40), (1, 39), (1, 38))
    assert DISCOVERY_SEQUENCE[39] == (1, 1)
    assert DISCOVERY_SEQUENCE[40] == (2, 40)
    assert DISCOVERY_SEQUENCE[79] == (2, 1)
    assert DISCOVERY_SEQUENCE[80] == (3, 40)
    assert DISCOVERY_SEQUENCE[-1] == (3, 1)


def test_step_advances_cursor_only_after_verified_navigation_and_complete_read(tmp_path: Path) -> None:
    database, navigation, browser, scan = service(tmp_path)
    started = scan.start(scan_id="scan-1")
    assert started.cursor_index == 0
    result = scan.step("scan-1")
    assert result.processed is True
    assert (result.galaxy, result.solar) == (1, 40)
    assert result.scan.status == "running"
    assert result.scan.cursor_index == 1
    assert navigation.calls == [(1, 40)]
    assert browser.calls == [(1, 40)]
    database.close()


def test_ambiguous_navigation_stops_without_read_or_cursor_advance(tmp_path: Path) -> None:
    database, navigation, browser, scan = service(tmp_path)
    scan.start(scan_id="scan-ambiguous")
    navigation.next_status = "ambiguous"
    result = scan.step("scan-ambiguous")
    assert result.processed is False
    assert result.scan.status == "ambiguous"
    assert result.scan.cursor_index == 0
    assert navigation.calls == [(1, 40)]
    assert browser.calls == []
    database.close()


def test_partial_square_info_is_failed_safe_and_never_claims_empty_system(tmp_path: Path) -> None:
    database, navigation, browser, scan = service(tmp_path)
    scan.start(scan_id="scan-partial")
    browser.visible = 2
    browser.readable = 1
    result = scan.step("scan-partial")
    assert result.processed is False
    assert result.scan.status == "failed_safe"
    assert result.scan.cursor_index == 0
    assert "Partial system evidence" in result.scan.detail
    assert scan.last_completed() is None
    database.close()


def test_run_max_steps_preserves_deterministic_persistent_cursor(tmp_path: Path) -> None:
    database, navigation, browser, scan = service(tmp_path)
    scan.start(scan_id="scan-two")
    result = scan.run("scan-two", max_steps=2)
    assert result.status == "running"
    assert result.cursor_index == 2
    assert navigation.calls == [(1, 40), (1, 39)]
    assert browser.calls == [(1, 40), (1, 39)]
    database.close()


def test_existing_unresolved_navigation_marks_running_scan_ambiguous_without_new_effect(tmp_path: Path) -> None:
    database, navigation, browser, scan = service(tmp_path)
    scan.start(scan_id="scan-nav-blocked")
    navigation.unresolved_rows = (SimpleNamespace(request_id="nav-x", status="ambiguous"),)
    result = scan.step("scan-nav-blocked")
    assert result.scan.status == "ambiguous"
    assert result.scan.cursor_index == 0
    assert navigation.calls == []
    assert browser.calls == []
    database.close()
