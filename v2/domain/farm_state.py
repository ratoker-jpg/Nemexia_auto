from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class FarmPhase(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    NO_TARGETS_WAIT = "no_targets_wait"
    SENDING = "sending"
    WAITING_RETURN = "waiting_return"
    CAPTCHA = "captcha"
    ERROR = "error"
    STOPPED = "stopped"


class FarmEventKind(str, Enum):
    START_SCAN = "start_scan"
    NO_TARGETS = "no_targets"
    START_SEND = "start_send"
    WAVE_SENT = "wave_sent"
    CAPTCHA = "captcha"
    ERROR = "error"
    STOP = "stop"
    RESET = "reset"


@dataclass(frozen=True)
class FarmSnapshot:
    phase: FarmPhase = FarmPhase.IDLE
    targets_found: int = 0
    fleet_used: int | None = None
    fleet_max: int | None = None
    last_wave_sent: int = 0
    next_scan_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class FarmEvent:
    kind: FarmEventKind
    targets_found: int | None = None
    fleet_used: int | None = None
    fleet_max: int | None = None
    sent: int | None = None
    next_scan_at: datetime | None = None
    error: str | None = None


def reduce_farm_state(state: FarmSnapshot, event: FarmEvent) -> FarmSnapshot:
    """Apply a typed farm event without depending on UI text.

    This reducer is intentionally side-effect free. The existing Tkinter farm
    runtime is not wired to it yet; V2 controllers will adopt it incrementally.
    """
    common = {
        "fleet_used": state.fleet_used if event.fleet_used is None else max(0, event.fleet_used),
        "fleet_max": state.fleet_max if event.fleet_max is None else max(0, event.fleet_max),
    }

    if event.kind == FarmEventKind.START_SCAN:
        return replace(
            state,
            phase=FarmPhase.SCANNING,
            targets_found=0,
            next_scan_at=None,
            error=None,
            **common,
        )
    if event.kind == FarmEventKind.NO_TARGETS:
        return replace(
            state,
            phase=FarmPhase.NO_TARGETS_WAIT,
            targets_found=0,
            next_scan_at=event.next_scan_at,
            error=None,
            **common,
        )
    if event.kind == FarmEventKind.START_SEND:
        return replace(
            state,
            phase=FarmPhase.SENDING,
            targets_found=max(0, event.targets_found or state.targets_found),
            error=None,
            **common,
        )
    if event.kind == FarmEventKind.WAVE_SENT:
        return replace(
            state,
            phase=FarmPhase.WAITING_RETURN,
            last_wave_sent=max(0, event.sent or 0),
            next_scan_at=event.next_scan_at,
            error=None,
            **common,
        )
    if event.kind == FarmEventKind.CAPTCHA:
        return replace(state, phase=FarmPhase.CAPTCHA, error=event.error, **common)
    if event.kind == FarmEventKind.ERROR:
        return replace(state, phase=FarmPhase.ERROR, error=event.error or "Unknown error", **common)
    if event.kind == FarmEventKind.STOP:
        return replace(state, phase=FarmPhase.STOPPED, next_scan_at=None, **common)
    if event.kind == FarmEventKind.RESET:
        return FarmSnapshot()
    raise ValueError(f"Unsupported farm event: {event.kind!r}")
