from __future__ import annotations

from pathlib import Path

import pytest

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.navigation import NavigationCoordinator, NavigationObservation
from v2.persistence.database import V2Database, V2DatabaseError
from v2.persistence.navigation_journal import NavigationJournalRepository


class _Backend:
    def __init__(self) -> None:
        identity = build_browser_identity(
            endpoint="http://127.0.0.1:9222",
            page_url="https://game.ares.nemexia.com/fleets.php",
            page_count=1,
            game_page_count=1,
            planets=(PlanetDomFact("101", "3:39:11", "HOME", True),),
            trigger_coord="3:39:11",
        )
        self.observation = NavigationObservation("runtime-page:123", identity)
        self.closed = False

    def observe(self) -> NavigationObservation:
        return self.observation

    def close(self) -> None:
        self.closed = True


def test_navigation_journal_is_persistent_and_request_id_is_immutable(tmp_path: Path) -> None:
    db_path = tmp_path / "v2.sqlite3"
    with V2Database(db_path) as database:
        repo = NavigationJournalRepository(database)
        assert database.schema_version() == 9
        assert {"navigation_actions", "navigation_schema_migrations"}.issubset(database.table_names())
        version = database._require_conn().execute(
            "SELECT MAX(version) FROM navigation_schema_migrations"
        ).fetchone()[0]
        assert int(version) == 1

        pending = repo.begin(
            request_id="nav-1",
            action_kind="switch_planet",
            before={"planet_id": "101"},
            intent={"planet_id": "202"},
        )
        assert pending.status == "pending"
        with pytest.raises(V2DatabaseError, match="already exists"):
            repo.begin(
                request_id="nav-1",
                action_kind="switch_planet",
                before={"planet_id": "101"},
                intent={"planet_id": "202"},
            )
        ambiguous = repo.finish("nav-1", status="ambiguous", detail="remote effect unknown")
        assert ambiguous.status == "ambiguous"
        assert repo.unresolved()[0].request_id == "nav-1"

    with V2Database(db_path) as reopened:
        repo = NavigationJournalRepository(reopened)
        record = repo.read("nav-1")
        assert record is not None
        assert record.status == "ambiguous"
        assert record.intent == {"planet_id": "202"}


def test_coordinator_captures_before_context_and_keeps_backend_behind_mutex(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as database:
        backend = _Backend()
        coordinator = NavigationCoordinator(backend, NavigationJournalRepository(database))
        record = coordinator.begin_request(
            request_id="bind-1",
            action_kind="bind_session",
            intent={"reason": "production ownership"},
        )
        assert record.before["page_token"] == "runtime-page:123"
        assert record.before["account_fingerprint"]
        assert record.before["planet_id"] == "101"
        assert coordinator.record("bind-1") == record
        completed = coordinator.finish_request("bind-1", status="verified", detail="same bound page")
        assert completed.status == "verified"
        assert completed.after is not None
        coordinator.close()
        assert backend.closed is True


def test_navigation_backend_stays_single_owned_surface_after_auto04() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_navigation_backend.py").read_text(encoding="utf-8")
    app = (root / "app_qt.py").read_text(encoding="utf-8")

    assert "_bound_page" in source
    assert "len(candidates) != 1" in source
    assert "runtime-page:" in source
    assert "V2NavigationCdpBackend" in app
    assert "NavigationJournalRepository" in app
    assert "NavigationCoordinator" in app
    assert source.count(".goto(") == 1
    assert "change_planet.php" in source

    for forbidden in (
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "refreshGalaxy(",
        "processSpy(",
        "SendFleet(",
    ):
        assert forbidden not in source
