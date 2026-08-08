from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.application.asteroid_actions import (
    AsteroidActionService,
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchPreparation,
    AsteroidDispatchRejected,
)
from v2.application.asteroid_journal import AsteroidRequestBlocked, AsteroidRequestCoordinator
from v2.application.debris_dispatch import DebrisDispatchReuseGate
from v2.application.debris_source import V2DebrisSource
from v2.domain.asteroids import AsteroidObservationFact, movement_margin_seconds
from v2.domain.debris import DebrisObservationFact, DebrisReadState
from v2.domain.debris_candidates import DebrisCandidate
from v2.infrastructure.cdp_debris_reader import snapshot_from_raw
from v2.persistence.database import V2Database


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
OBSERVED = datetime(2026, 8, 8, 8, 30, tzinfo=UTC)


READY_TOOLTIP = """
<div>Информация об астероиде</div>
<div>Последнее перемещение 2026-08-08 12:00:00</div>
<div>Следующее перемещение 2026-08-08 13:00:00</div>
<div>Скорость 60 Минут / поле</div>
<div>Этот астероид содержит обломки</div>
"""
NO_DEBRIS_TOOLTIP = READY_TOOLTIP.replace(
    "<div>Этот астероид содержит обломки</div>", ""
)
PARTIAL_TOOLTIP = """
<div>Информация об астероиде</div>
<div>Этот астероид содержит обломки</div>
"""


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def observation() -> AsteroidObservationFact:
    return AsteroidObservationFact(
        galaxy=2,
        system=23,
        position=8,
        last_move_at=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
        next_move_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        period_seconds=3600,
        observed_at=OBSERVED,
    )


def candidate() -> DebrisCandidate:
    fact = DebrisObservationFact(asteroid=observation())
    return DebrisCandidate(fact, 2, 23, 8, 0, True)


def preparation() -> AsteroidDispatchPreparation:
    obs = observation()
    prepared_at = datetime(2026, 8, 8, 8, 40, tzinfo=UTC)
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
        movement_margin_seconds=movement_margin_seconds(
            obs.next_move_at, obs.period_seconds, arrival_at
        ),
    )


class SimulatedCrash(BaseException):
    pass


class Backend:
    def __init__(self, mode: str = "pending_crash") -> None:
        self.mode = mode
        self.prepare_calls = 0
        self.dispatch_calls = 0

    def prepare(self, _command):
        self.prepare_calls += 1
        return preparation()

    def dispatch(self, _command, _preparation):
        self.dispatch_calls += 1
        if self.mode == "pending_crash":
            raise SimulatedCrash("process terminated after pending journal commit")
        if self.mode == "ambiguous":
            raise AsteroidDispatchAmbiguous("unknown after possible acceptance")
        if self.mode == "unknown":
            raise RuntimeError("connection lost after possible acceptance")
        if self.mode == "captcha_before_acceptance":
            raise AsteroidCaptchaBlocked("CAPTCHA before acceptance")
        if self.mode == "moved":
            raise AsteroidDispatchRejected("Asteroid target устарел перед SendFleet")
        if self.mode == "recyclers":
            raise AsteroidDispatchRejected("Недостаточно переработчиков перед SendFleet")
        if self.mode == "capacity":
            raise AsteroidDispatchRejected("Нет свободных слотов флота перед SendFleet")
        raise AssertionError(f"unsupported mode: {self.mode}")

    def close(self) -> None:
        return None


class BlockingBackend:
    def __init__(self) -> None:
        self.prepare_calls = 0
        self.dispatch_calls = 0

    def prepare(self, _command):
        self.prepare_calls += 1
        return preparation()

    def dispatch(self, _command, _preparation):
        self.dispatch_calls += 1
        raise AssertionError("unresolved debris trajectory must block before remote dispatch")

    def close(self) -> None:
        return None


class FakeDebrisBackend:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot

    def read_debris(self):
        return self.snapshot


def gate(db: V2Database, backend) -> DebrisDispatchReuseGate:
    coordinator = AsteroidRequestCoordinator(
        AsteroidActionService(backend, enabled=True), db
    )
    return DebrisDispatchReuseGate(coordinator)


def dispatch(gate_: DebrisDispatchReuseGate, request_id: str) -> None:
    gate_.dispatch(
        candidate(),
        source="2:22:3",
        recycler_count=5,
        safety_seconds=10,
        request_id=request_id,
    )


def test_pending_debris_attempt_survives_restart_and_blocks_second_side_effect(tmp_path) -> None:
    path = tmp_path / "v2.sqlite3"
    with V2Database(path) as db:
        backend = Backend("pending_crash")
        reuse = gate(db, backend)
        with pytest.raises(SimulatedCrash):
            dispatch(reuse, "debris-pending")
        assert backend.dispatch_calls == 1
        assert reuse.record("debris-pending").status == "pending"

    with V2Database(path) as reopened:
        backend = BlockingBackend()
        reuse = gate(reopened, backend)
        with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
            dispatch(reuse, "debris-after-restart")
        assert backend.dispatch_calls == 0
        assert reuse.record("debris-pending").status == "pending"


def test_ambiguous_and_unknown_after_possible_acceptance_survive_restart(tmp_path) -> None:
    for mode in ("ambiguous", "unknown"):
        path = tmp_path / f"{mode}.sqlite3"
        with V2Database(path) as db:
            backend = Backend(mode)
            reuse = gate(db, backend)
            with pytest.raises((AsteroidDispatchAmbiguous, RuntimeError)):
                dispatch(reuse, f"debris-{mode}")
            assert backend.dispatch_calls == 1
            assert reuse.record(f"debris-{mode}").status == "ambiguous"

        with V2Database(path) as reopened:
            backend = BlockingBackend()
            reuse = gate(reopened, backend)
            with pytest.raises(AsteroidRequestBlocked, match="незавершённая"):
                dispatch(reuse, f"debris-{mode}-retry")
            assert backend.dispatch_calls == 0


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("moved", "устарел"),
        ("recyclers", "переработчиков"),
        ("capacity", "свободных слотов"),
        ("captcha_before_acceptance", "CAPTCHA"),
    ),
)
def test_proven_pre_acceptance_failures_are_failed_safe_without_retry_loop(
    tmp_path, mode: str, expected: str
) -> None:
    with V2Database(tmp_path / f"{mode}.sqlite3") as db:
        backend = Backend(mode)
        reuse = gate(db, backend)
        with pytest.raises((AsteroidDispatchRejected, AsteroidCaptchaBlocked), match=expected):
            dispatch(reuse, f"debris-{mode}")
        assert backend.dispatch_calls == 1
        record = reuse.record(f"debris-{mode}")
        assert record is not None and record.status == "failed_safe"
        assert expected.casefold() in record.detail.casefold()


def test_marker_missing_is_proven_no_debris_but_partial_marker_is_not() -> None:
    no_debris = snapshot_from_raw(
        {
            "server_time": [2026, 8, 8, 12, 30, 0],
            "asteroids": [
                {"g": 1, "s": 40, "p": 3, "tooltip": NO_DEBRIS_TOOLTIP}
            ],
        }
    )
    read = V2DebrisSource(FakeDebrisBackend(no_debris)).read()
    assert read.state is DebrisReadState.NO_DEBRIS
    assert read.complete_current_system_evidence

    partial = snapshot_from_raw(
        {
            "server_time": [2026, 8, 8, 12, 30, 0],
            "asteroids": [
                {"g": 1, "s": 40, "p": 3, "tooltip": PARTIAL_TOOLTIP}
            ],
        }
    )
    read = V2DebrisSource(FakeDebrisBackend(partial)).read()
    assert read.state is DebrisReadState.PARTIAL_EVIDENCE
    assert not read.complete_current_system_evidence


def test_runtime_never_claims_completed_120_system_scan_or_auto_navigates() -> None:
    combined = "\n".join(
        text(path)
        for path in (
            "v2/application/debris_source.py",
            "v2/application/debris_repository.py",
            "v2/application/debris_context.py",
            "v2/ui/pages/debris.py",
        )
    )
    for forbidden in (
        "120/120",
        "completed 120",
        "полный скан заверш",
        "Сканировать все системы",
        "refreshGalaxy",
        "ajax_galaxy.php",
        ".goto(",
        "new_page(",
    ):
        assert forbidden.casefold() not in combined.casefold()
    assert "Прочитать открытую систему" in combined
    assert "автоматический обход 3×40" in combined


def test_page_hide_input_change_and_window_close_disarm_future_debris_attempts() -> None:
    page = text("v2/ui/pages/debris.py")
    context = text("v2/application/debris_context.py")
    workflow = text("v2/application/debris_workflow.py")

    assert "def hideEvent" in page
    assert "self._request_manual_stop()" in page
    assert "self._invalidate_preparation()" in page
    assert 'getattr(self.context, "cancel_debris_preparation"' in page
    assert "def cancel_debris_preparation" in context
    assert "workflow.request_stop()" in context
    assert "workflow.cancel_prepared()" in context
    assert "def cancel_prepared" in workflow
    assert "self._confirmation_id = None" in workflow


def test_existing_discovery_persistence_coverage_remains_present() -> None:
    repository_tests = text("tests/test_v2_debris_repository.py")
    reader_tests = text("tests/test_v2_attach_only_debris_reader.py")
    workflow_tests = text("tests/test_v2_debris_workflow.py")

    for required in (
        "survives_restart",
        "exact_duplicates",
        "no_debris_never_erases_other_system_evidence",
        "reading_two_manually_opened_systems_accumulates_evidence",
    ):
        assert required in repository_tests
    assert "partial_square_info_stays_partial" in reader_tests
    assert "manual_stop_during_started_attempt_does_not_cancel_it_but_blocks_next" in workflow_tests
