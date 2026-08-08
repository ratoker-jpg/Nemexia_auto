from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds
from v2.persistence.database import V2Database


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def observation() -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
        next_move_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        period_seconds=3600,
        observed_at=datetime(2026, 8, 8, 8, 30, tzinfo=timezone.utc),
    )


def preparation() -> AsteroidDispatchPreparation:
    obs = observation()
    prepared_at = datetime(2026, 8, 8, 8, 40, tzinfo=timezone.utc)
    arrival_at = prepared_at + timedelta(seconds=300)
    return AsteroidDispatchPreparation(
        source="2:22:3",
        observation=obs,
        target="2:23:8",
        recycler_count=5,
        available_recyclers=20,
        free_fleet_slots=2,
        prepared_at=prepared_at,
        one_way_seconds=300,
        round_trip_seconds=600,
        shifts=0,
        arrival_at=arrival_at,
        return_at=prepared_at + timedelta(seconds=600),
        gas_needed=120,
        movement_margin_seconds=movement_margin_seconds(obs.next_move_at, obs.period_seconds, arrival_at),
    )


class SimulatedCrash(BaseException):
    pass


class CrashAfterPendingBackend:
    def __init__(self) -> None:
        self.dispatch_calls = 0

    def prepare(self, _command):
        return preparation()

    def dispatch(self, _command, _preparation):
        self.dispatch_calls += 1
        # Models process termination after pending was durably committed but before
        # application-level exception recovery could classify the remote attempt.
        raise SimulatedCrash("process terminated")

    def close(self) -> None:
        return None


class CountingBackend:
    def __init__(self) -> None:
        self.dispatch_calls = 0

    def prepare(self, _command):
        return preparation()

    def dispatch(self, _command, _preparation):
        self.dispatch_calls += 1
        raise AssertionError("unresolved restart guard must block before dispatch")

    def close(self) -> None:
        return None


def test_pending_crash_window_survives_restart_and_blocks_duplicate_side_effect(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    command = AsteroidDispatchCommand("2:22:3", observation(), 5, 10)

    with V2Database(path) as db:
        backend = CrashAfterPendingBackend()
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), db)
        with pytest.raises(SimulatedCrash):
            coordinator.dispatch(command, request_id="crash-window")
        record = coordinator.record("crash-window")
        assert backend.dispatch_calls == 1
        assert record is not None and record.status == "pending"

    with V2Database(path) as reopened:
        backend = CountingBackend()
        coordinator = AsteroidRequestCoordinator(AsteroidActionService(backend, enabled=True), reopened)
        with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
            coordinator.dispatch(command, request_id="restart-duplicate")
        assert backend.dispatch_calls == 0
        original = coordinator.record("crash-window")
        assert original is not None and original.status == "pending"


def test_live_pre_click_gate_covers_movement_capacity_recyclers_and_exact_verification() -> None:
    backend = text("v2/infrastructure/cdp_asteroid_backend.py")
    for required in (
        "await self._recheck_observation(command.observation",
        "_validated_pre_click_snapshot",
        "Asteroid target устарел перед SendFleet",
        "#ship_1_11_max",
        "#FleetsCount",
        "#MaxFleets",
        "Fleet composition изменена перед SendFleet",
        "select_verified_asteroid_flight(",
        'str(row["id"]) not in before_ids',
        'str(row.get("mission") or "").strip().casefold() == ASTEROID_MISSION_NAME.casefold()',
    ):
        assert required in backend


def test_captcha_after_possible_acceptance_stays_ambiguous_and_never_opens_retry() -> None:
    backend = text("v2/infrastructure/cdp_asteroid_backend.py")
    service = text("v2/application/asteroid_actions.py")
    workflow = text("v2/application/asteroid_workflow.py")
    assert "if await self._captcha_present(page):\n                break" in backend
    assert "exact new-flight verification отсутствует" in backend
    assert "AsteroidDispatchAmbiguous" in backend
    assert "AsteroidDispatchAmbiguous" in service
    assert "STOPPED_AMBIGUOUS" in workflow
    for forbidden in ("for attempt in", "retry_count", "max_retries"):
        assert forbidden not in backend
        assert forbidden not in workflow


def test_duplicate_candidate_and_dispatch_identities_are_persistently_guarded() -> None:
    candidates = text("v2/persistence/asteroid_candidates.py")
    journal = text("v2/persistence/asteroid_journal.py")
    assert "UNIQUE(" in candidates
    assert "idx_asteroid_actions_unresolved_identity" in journal
    assert "WHERE status IN ('pending','ambiguous')" in journal
    assert "INSERT OR IGNORE INTO asteroid_observations" in candidates


def test_asteroid_auto_repeat_remains_deferred_and_no_scheduler_can_start_on_restart() -> None:
    combined = "\n".join(
        text(path)
        for path in (
            "app_qt.py",
            "v2/application/asteroid_context.py",
            "v2/application/asteroid_workflow.py",
            "v2/ui/pages/asteroids.py",
        )
    )
    for forbidden in (
        "QTimer",
        "asteroid_auto_enabled",
        "asteroid_next_cycle_at",
        "run_asteroid_cycle",
        "_run_dynamic_asteroid_cycle",
    ):
        assert forbidden not in combined
    assert "should_stop" in combined
    assert "STOPPED_MANUAL" in combined


def test_default_launcher_and_debris_boundary_remain_controlled() -> None:
    launcher = text("run_app.bat")
    window = text("v2/ui/main_window.py")
    debris_page = text("v2/ui/pages/debris.py")
    debris_context = text("v2/application/debris_context.py")
    assert "app_entry.py" in launcher
    assert "app_qt.py" not in launcher
    assert 'if key == "debris":' in window
    assert "return DebrisPage(self.context, self)" in window
    assert "AsteroidRequestCoordinator(self._asteroid_actions, database)" in debris_context
    for forbidden in (
        "playwright",
        "SendFleetButton",
        "refreshGalaxy",
        ".goto(",
        "new_page(",
        "ajax_galaxy.php",
    ):
        assert forbidden not in debris_page
