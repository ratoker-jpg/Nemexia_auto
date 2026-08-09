from __future__ import annotations

from pathlib import Path

from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness
from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.debris_context import DebrisEnabledApplicationContext
from v2.application.galaxy_navigation import VerifiedGalaxyNavigationCoordinator
from v2.application.navigation import (
    NavigationMutationError,
    NavigationObservation,
    NavigationPageState,
)
from v2.persistence.database import V2Database
from v2.persistence.navigation_journal import NavigationJournalRepository


def observation(*, galaxy: int = 3, solar: int = 39) -> NavigationObservation:
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url=f"https://game.ares.nemexia.com/galaxy.php?galaxy={galaxy}&solar={solar}",
        page_count=1,
        game_page_count=1,
        planets=(PlanetDomFact("101", "3:39:11", "HOME", True),),
        trigger_coord="3:39:11",
    )
    return NavigationObservation(
        "runtime-page:galaxy",
        identity,
        NavigationPageState(
            page_kind="galaxy",
            galaxy_ready=True,
            galaxy=galaxy,
            solar=solar,
        ),
    )


class Backend:
    def __init__(self) -> None:
        self.current = observation()
        self.calls: list[tuple[int, int]] = []
        self.error: Exception | None = None

    def observe(self):
        return self.current

    def navigate_galaxy_system(self, *, galaxy: int, solar: int, **_kwargs):
        self.calls.append((galaxy, solar))
        if self.error is not None:
            raise self.error
        self.current = observation(galaxy=galaxy, solar=solar)
        return self.current

    def close(self):
        pass


def coordinator(tmp_path: Path, backend: Backend):
    database = V2Database(tmp_path / "v2.sqlite3")
    nav = VerifiedGalaxyNavigationCoordinator(
        backend,
        NavigationJournalRepository(database),
    )
    return database, nav


def test_success_attempts_one_system_mutation_and_verifies_exact_destination(tmp_path: Path) -> None:
    backend = Backend()
    database, nav = coordinator(tmp_path, backend)
    record = nav.navigate_galaxy_system(
        request_id="galaxy-1",
        galaxy=2,
        solar=40,
    )
    assert record.status == "verified"
    assert record.action_kind == "galaxy_system"
    assert backend.calls == [(2, 40)]
    assert record.before["galaxy"] == 3
    assert record.before["solar"] == 39
    assert record.after is not None
    assert record.after["galaxy"] == 2
    assert record.after["solar"] == 40
    database.close()


def test_same_system_is_verified_without_remote_effect(tmp_path: Path) -> None:
    backend = Backend()
    database, nav = coordinator(tmp_path, backend)
    record = nav.navigate_galaxy_system(
        request_id="galaxy-same",
        galaxy=3,
        solar=39,
    )
    assert record.status == "verified"
    assert backend.calls == []
    assert "no remote effect" in record.detail
    database.close()


def test_invalid_solar_is_failed_safe_before_backend_call(tmp_path: Path) -> None:
    backend = Backend()
    database, nav = coordinator(tmp_path, backend)
    record = nav.navigate_galaxy_system(
        request_id="galaxy-invalid",
        galaxy=1,
        solar=41,
    )
    assert record.status == "failed_safe"
    assert backend.calls == []
    database.close()


def test_pre_attempt_backend_error_is_failed_safe(tmp_path: Path) -> None:
    backend = Backend()
    backend.error = NavigationMutationError("CAPTCHA before refresh", remote_attempted=False)
    database, nav = coordinator(tmp_path, backend)
    record = nav.navigate_galaxy_system(
        request_id="galaxy-captcha",
        galaxy=1,
        solar=1,
    )
    assert record.status == "failed_safe"
    assert backend.calls == [(1, 1)]
    database.close()


def test_post_attempt_error_is_ambiguous_without_retry(tmp_path: Path) -> None:
    backend = Backend()
    backend.error = NavigationMutationError("ajax result unknown", remote_attempted=True)
    database, nav = coordinator(tmp_path, backend)
    record = nav.navigate_galaxy_system(
        request_id="galaxy-ambiguous",
        galaxy=1,
        solar=1,
    )
    assert record.status == "ambiguous"
    assert backend.calls == [(1, 1)]
    assert "automatic retry forbidden" in record.detail
    database.close()


def test_readiness_context_leaves_navigation_shutdown_to_debris_superclass(monkeypatch) -> None:
    context = object.__new__(DebrisEnabledApplicationContextWithReadiness)
    sentinel = object()
    context._navigation_coordinator = sentinel
    context._automatic_recon = object()
    seen: list[object] = []

    def fake_super_close(self) -> None:
        seen.append(self._navigation_coordinator)
        self._navigation_coordinator = None

    monkeypatch.setattr(DebrisEnabledApplicationContext, "close", fake_super_close)
    context.close()

    assert seen == [sentinel]
    assert context._navigation_coordinator is None
    assert context._automatic_recon is None


def test_auto09_source_contract_has_one_refresh_effect_and_no_ui_browser_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = (root / "v2/infrastructure/cdp_galaxy_navigation.py").read_text(encoding="utf-8")
    service = (root / "v2/application/galaxy_navigation.py").read_text(encoding="utf-8")
    context = (root / "v2/application/automation_context.py").read_text(encoding="utf-8")
    app = (root / "app_qt.py").read_text(encoding="utf-8")

    assert backend.count("window.refreshGalaxy();") == 1
    assert "ajax_galaxy.php" in backend
    assert "#galaxyHolder" in backend
    assert "#c1" in backend and "#c2" in backend
    assert ".goto(" not in backend
    assert "navigate_galaxy_system" in service
    assert 'action_kind="galaxy_system"' in service
    assert "VerifiedGalaxyNavigationCoordinator as NavigationCoordinator" in app
    assert "navigate_galaxy_system" in context

    for forbidden in (
        "playwright",
        "document.querySelector",
        "window.refreshGalaxy",
        "ajax_galaxy.php",
    ):
        assert forbidden not in service
        assert forbidden not in context
