from __future__ import annotations

from datetime import datetime, timezone

from v2.persistence.database import V2Database
from v2.persistence.rest_mode import (
    REST_MODE_ATTACK_UNVERIFIED,
    RestModeRepository,
)


def _iso(hour: int = 12) -> str:
    return datetime(2026, 8, 10, hour, 0, tzinfo=timezone.utc).isoformat()


def test_rest_mode_component_schema_is_versioned_and_startup_is_disarmed(tmp_path) -> None:
    path = tmp_path / "v2.sqlite3"
    db = V2Database(path)
    repo = RestModeRepository(db)
    repo.begin_start(
        session_id="rest-mode:one",
        server_host="game.ares.nemexia.com",
        account_fingerprint="account-a",
        planet_id="17",
        planet_coord="3:39:11",
        started_at=_iso(),
    )
    repo.save_observation(
        status="ACTIVITY_WARNING",
        armed=True,
        activity_minutes=20,
        activity_epoch=7,
        warning_sent=True,
        observed_at=_iso(),
        next_check_at=_iso(13),
        detail="warning",
    )
    db.close()

    reopened = V2Database(path)
    recovered = RestModeRepository(reopened)
    state = recovered.disarm_on_startup()
    assert state.armed is False
    assert state.status == "DISARMED"
    assert state.next_check_at is None
    assert state.account_fingerprint == "account-a"
    assert state.planet_id == "17"
    assert state.planet_coord == "3:39:11"
    assert state.activity_epoch == 7
    assert state.activity_warning_sent is True
    assert state.last_activity_minutes == 20
    assert state.attack_watch_state == REST_MODE_ATTACK_UNVERIFIED
    assert "explicit Start required" in state.detail

    tables = {
        str(row[0])
        for row in reopened._require_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "rest_mode_schema_migrations" in tables
    assert "rest_mode_state" in tables
    reopened.close()


def test_same_identity_preserves_observation_dedupe_but_new_identity_clears_it(tmp_path) -> None:
    db = V2Database(tmp_path / "v2.sqlite3")
    repo = RestModeRepository(db)
    repo.begin_start(
        session_id="first",
        server_host="game.ares.nemexia.com",
        account_fingerprint="account-a",
        planet_id="17",
        planet_coord="3:39:11",
        started_at=_iso(),
    )
    repo.save_observation(
        status="ACTIVITY_WARNING",
        armed=True,
        activity_minutes=15,
        activity_epoch=4,
        warning_sent=True,
        observed_at=_iso(),
        next_check_at=_iso(13),
    )
    repo.stop()

    same = repo.begin_start(
        session_id="second",
        server_host="game.ares.nemexia.com",
        account_fingerprint="account-a",
        planet_id="17",
        planet_coord="3:39:11",
        started_at=_iso(13),
    )
    assert same.activity_epoch == 4
    assert same.activity_warning_sent is True
    assert same.last_success_at == _iso()
    assert same.last_activity_minutes == 15

    changed = repo.begin_start(
        session_id="third",
        server_host="game.ares.nemexia.com",
        account_fingerprint="account-a",
        planet_id="18",
        planet_coord="3:39:12",
        started_at=_iso(14),
    )
    assert changed.activity_epoch == 0
    assert changed.activity_warning_sent is False
    assert changed.last_success_at is None
    assert changed.last_activity_minutes is None

    failed_new_identity = repo.block(
        status="BLOCKED_BROWSER",
        detail="New planet readiness failed",
    )
    assert failed_new_identity.planet_id == "18"
    assert failed_new_identity.planet_coord == "3:39:12"
    assert failed_new_identity.last_success_at is None
    assert failed_new_identity.last_activity_minutes is None
    db.close()
