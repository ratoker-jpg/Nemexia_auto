from datetime import datetime, timezone

from v2.domain.farm_state import (
    FarmEvent,
    FarmEventKind,
    FarmPhase,
    FarmSnapshot,
    reduce_farm_state,
)


def test_farm_state_is_driven_by_typed_events() -> None:
    state = reduce_farm_state(FarmSnapshot(), FarmEvent(FarmEventKind.START_SCAN))
    assert state.phase is FarmPhase.SCANNING

    deadline = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    state = reduce_farm_state(
        state,
        FarmEvent(FarmEventKind.NO_TARGETS, next_scan_at=deadline),
    )
    assert state.phase is FarmPhase.NO_TARGETS_WAIT
    assert state.next_scan_at == deadline


def test_wave_sent_records_capacity_and_next_scan_without_ui_text() -> None:
    deadline = datetime(2026, 8, 8, 13, 0, tzinfo=timezone.utc)
    state = reduce_farm_state(
        FarmSnapshot(phase=FarmPhase.SENDING),
        FarmEvent(
            FarmEventKind.WAVE_SENT,
            sent=2,
            fleet_used=22,
            fleet_max=22,
            next_scan_at=deadline,
        ),
    )

    assert state.phase is FarmPhase.WAITING_RETURN
    assert state.last_wave_sent == 2
    assert (state.fleet_used, state.fleet_max) == (22, 22)
    assert state.next_scan_at == deadline


def test_captcha_and_error_are_explicit_terminal_states() -> None:
    captcha = reduce_farm_state(
        FarmSnapshot(phase=FarmPhase.SCANNING),
        FarmEvent(FarmEventKind.CAPTCHA, error="human check"),
    )
    assert captcha.phase is FarmPhase.CAPTCHA
    assert captcha.error == "human check"

    failed = reduce_farm_state(
        FarmSnapshot(),
        FarmEvent(FarmEventKind.ERROR, error="browser disconnected"),
    )
    assert failed.phase is FarmPhase.ERROR
    assert failed.error == "browser disconnected"


def test_reset_returns_clean_idle_snapshot() -> None:
    dirty = FarmSnapshot(
        phase=FarmPhase.ERROR,
        targets_found=9,
        fleet_used=20,
        fleet_max=22,
        last_wave_sent=2,
        error="x",
    )
    assert reduce_farm_state(dirty, FarmEvent(FarmEventKind.RESET)) == FarmSnapshot()
