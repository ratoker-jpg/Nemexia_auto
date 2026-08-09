from pathlib import Path

from v2.persistence.asteroid_autorenew import AsteroidAutorenewRepository
from v2.persistence.database import V2Database


def test_persisted_armed_state_is_always_disarmed_on_startup(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    database = V2Database(path)
    repo = AsteroidAutorenewRepository(database)
    armed = repo.arm(
        session_id="session-1",
        source_planet_id="101",
        source_coord="3:39:8",
        account_fingerprint="acct",
        recycler_count=5,
        max_flights=15,
        safety_seconds=10,
        buffer_minutes=5,
    )
    assert armed.armed is True
    database.close()

    reopened = V2Database(path)
    repo2 = AsteroidAutorenewRepository(reopened)
    recovered = repo2.disarm_on_startup()
    assert recovered.armed is False
    assert recovered.status == "disarmed_restart"
    assert recovered.next_cycle_at is None
    assert "explicit Start" in recovered.detail
    reopened.close()


def test_stop_clears_future_due_time(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    repo = AsteroidAutorenewRepository(database)
    repo.arm(
        session_id="session-2",
        source_planet_id="101",
        source_coord="3:39:8",
        account_fingerprint="acct",
        recycler_count=5,
        max_flights=15,
        safety_seconds=10,
        buffer_minutes=5,
    )
    repo.transition(
        status="waiting_return",
        armed=True,
        next_cycle_at="2026-08-10T00:00:00+00:00",
        last_return_at="2026-08-09T23:55:00+00:00",
        verified_sent=3,
        detail="waiting",
    )
    stopped = repo.stop(status="stopped_manual", detail="operator")
    assert stopped.armed is False
    assert stopped.status == "stopped_manual"
    assert stopped.next_cycle_at is None
    database.close()
