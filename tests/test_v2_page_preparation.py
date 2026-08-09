from __future__ import annotations

from pathlib import Path

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.navigation import (
    NavigationCoordinator,
    NavigationMutationError,
    NavigationObservation,
    NavigationPageState,
)
from v2.persistence.database import V2Database
from v2.persistence.navigation_journal import NavigationJournalRepository


def _identity(page_url: str = "https://game.ares.nemexia.com/overview.php"):
    return build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url=page_url,
        page_count=1,
        game_page_count=1,
        planets=(PlanetDomFact("101", "3:39:11", "HOME", True),),
        trigger_coord="3:39:11",
    )


def _observation(kind: str) -> NavigationObservation:
    state = NavigationPageState(
        page_kind=kind,
        fleets_ready=kind == "fleets",
        options_ready=kind in {"options", "messages"},
        messages_ready=kind == "messages",
        galaxy_ready=kind == "galaxy",
        galaxy=3 if kind == "galaxy" else None,
        solar=39 if kind == "galaxy" else None,
    )
    page_name = "options" if kind == "messages" else kind
    return NavigationObservation(
        "runtime-page:77",
        _identity(f"https://game.ares.nemexia.com/{page_name}.php"),
        state,
    )


class _Backend:
    def __init__(self, kind: str = "other", *, preflight_failure: bool = False) -> None:
        self.current = _observation(kind)
        self.prepare_calls: list[str] = []
        self.message_calls = 0
        self.preflight_failure = preflight_failure
        self.closed = False

    def observe(self) -> NavigationObservation:
        return self.current

    def switch_planet(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("switch_planet is outside AUTO-05 page-prep tests")

    def prepare_page(self, *, page_kind: str, **kwargs) -> NavigationObservation:
        self.prepare_calls.append(page_kind)
        if self.preflight_failure:
            raise NavigationMutationError("page context changed", remote_attempted=False)
        self.current = _observation(page_kind)
        return self.current

    def prepare_system_messages(self, **kwargs) -> NavigationObservation:
        self.message_calls += 1
        self.current = _observation("messages")
        return self.current

    def close(self) -> None:
        self.closed = True


def _coordinator(tmp_path: Path, backend: _Backend):
    database = V2Database(tmp_path / "v2.sqlite3")
    coordinator = NavigationCoordinator(backend, NavigationJournalRepository(database))
    return database, coordinator


def test_prepare_fleets_is_one_journaled_page_effect(tmp_path: Path) -> None:
    backend = _Backend("other")
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.prepare_fleets(request_id="prep-fleets-1")
        assert record.status == "verified"
        assert backend.prepare_calls == ["fleets"]
        assert record.intent["page_kind"] == "fleets"
        assert record.before["planet_id"] == "101"
        assert record.after is not None and record.after["fleets_ready"] is True
    finally:
        coordinator.close()
        database.close()


def test_already_ready_page_has_zero_remote_effect(tmp_path: Path) -> None:
    backend = _Backend("galaxy")
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.prepare_galaxy(request_id="prep-galaxy-1")
        assert record.status == "verified"
        assert backend.prepare_calls == []
        assert "no remote navigation" in record.detail
    finally:
        coordinator.close()
        database.close()


def test_pre_attempt_page_failure_is_failed_safe(tmp_path: Path) -> None:
    backend = _Backend("other", preflight_failure=True)
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        record = coordinator.prepare_fleets(request_id="prep-fail-1")
        assert record.status == "failed_safe"
        assert backend.prepare_calls == ["fleets"]
        assert coordinator.unresolved() == ()
    finally:
        coordinator.close()
        database.close()


def test_system_messages_uses_two_separate_journal_requests(tmp_path: Path) -> None:
    backend = _Backend("other")
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        result = coordinator.prepare_system_messages(request_id="prep-msg-1")
        assert result.verified is True
        assert backend.prepare_calls == ["options"]
        assert backend.message_calls == 1
        assert result.page.request_id == "prep-msg-1"
        assert result.page.intent["phase"] == "options_page"
        assert result.system_tab is not None
        assert result.system_tab.request_id == "prep-msg-1:system-tab"
        assert result.system_tab.intent["phase"] == "system_tab"
        assert result.system_tab.after is not None
        assert result.system_tab.after["messages_ready"] is True
    finally:
        coordinator.close()
        database.close()


def test_loaded_system_messages_do_not_reload_remote_content(tmp_path: Path) -> None:
    backend = _Backend("messages")
    database, coordinator = _coordinator(tmp_path, backend)
    try:
        result = coordinator.prepare_system_messages(request_id="prep-msg-ready")
        assert result.verified is True
        assert backend.prepare_calls == []
        assert backend.message_calls == 0
    finally:
        coordinator.close()
        database.close()


def test_auto05_backend_has_one_generic_goto_and_one_system_load() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_navigation_backend.py").read_text(encoding="utf-8")

    assert "_bind_existing_game_page" in source
    assert "_bind_existing_fleets_page" not in source
    assert source.count(".goto(") == 1
    assert "'/fleets.php'" in source or '"/fleets.php"' in source
    assert "'/options.php'" in source or '"/options.php"' in source
    assert "'/galaxy.php'" in source or '"/galaxy.php"' in source
    assert source.count("loadTabContent('TabAdministrative', 2, 0)") == 1
    assert "#FleetsCount" in source and "#MaxFleets" in source
    assert "#messagesFolders" in source
    assert "#galaxyHolder" in source and "#c1" in source and "#c2" in source
    assert "refreshGalaxy(" not in source
    assert "processSpy(" not in source
    assert "SendFleet(" not in source
