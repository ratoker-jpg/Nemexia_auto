from __future__ import annotations

from datetime import datetime, timezone

import pytest

from v2.application.automation_authority import (
    AUTOFARM_OWNER,
    REST_MODE_OWNER,
    AutomationAuthority,
)
from v2.application.rest_mode import RestModeCycleResult
from v2.application.rest_mode_context import RestModeApplicationContext
from v2.persistence.rest_mode import REST_MODE_ATTACK_UNVERIFIED, RestModeState


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc).isoformat()


def _state(*, armed: bool, status: str) -> RestModeState:
    return RestModeState(
        armed=armed,
        status=status,
        session_id="rest-mode:test",
        server_host="game.ares.nemexia.com",
        account_fingerprint="account-a",
        planet_id="17",
        planet_coord="3:39:11",
        started_at=NOW,
        last_success_at=NOW if armed else None,
        next_check_at=None,
        last_activity_minutes=60 if armed else None,
        activity_epoch=0,
        activity_warning_sent=False,
        attack_watch_state=REST_MODE_ATTACK_UNVERIFIED,
        last_error="",
        blocking_navigation_request_id="",
        detail=status,
        updated_at=NOW,
    )


class FakeRestMode:
    def __init__(self, start_state=None, tick_state=None) -> None:
        self.current = start_state or _state(armed=False, status="DISARMED")
        self.start_state = start_state or _state(armed=True, status="WATCHING")
        self.tick_state = tick_state or self.start_state
        self.context = None
        self.stop_owner_during_call = None

    def state(self):
        return self.current

    def start(self, **_kwargs):
        self.current = self.start_state
        return RestModeCycleResult(self.current)

    def tick(self, **_kwargs):
        self.current = self.tick_state
        return RestModeCycleResult(self.current)

    def block_busy(self, detail):
        self.current = _state(armed=False, status="BLOCKED_BUSY")
        return self.current

    def stop(self, **_kwargs):
        if self.context is not None:
            self.stop_owner_during_call = self.context.automation_cycle_owner()
        self.current = _state(armed=False, status="DISARMED")
        return self.current


def _context(service: FakeRestMode, authority: AutomationAuthority | None = None):
    context = object.__new__(RestModeApplicationContext)
    context._rest_mode = service
    context._automation_authority = authority or AutomationAuthority()
    service.context = context
    return context


def test_start_holds_rest_mode_authority_only_while_armed() -> None:
    service = FakeRestMode(start_state=_state(armed=True, status="WATCHING"))
    context = _context(service)
    result = context.start_rest_mode()
    assert result.state.armed is True
    assert context.automation_cycle_owner() == REST_MODE_OWNER

    context.stop_rest_mode()
    assert service.stop_owner_during_call == REST_MODE_OWNER
    assert context.automation_cycle_owner() is None


def test_failed_or_blocked_start_releases_any_acquired_rest_authority() -> None:
    service = FakeRestMode(start_state=_state(armed=False, status="CAPTCHA_REQUIRED"))
    context = _context(service)
    result = context.start_rest_mode()
    assert result.state.status == "CAPTCHA_REQUIRED"
    assert context.automation_cycle_owner() is None


def test_busy_start_does_not_steal_or_release_other_owner() -> None:
    authority = AutomationAuthority()
    authority.acquire(AUTOFARM_OWNER)
    service = FakeRestMode()
    context = _context(service, authority)

    result = context.start_rest_mode()
    assert result.state.status == "BLOCKED_BUSY"
    assert context.automation_cycle_owner() == AUTOFARM_OWNER


def test_disarming_tick_releases_rest_authority_after_service_returns() -> None:
    service = FakeRestMode(
        start_state=_state(armed=True, status="WATCHING"),
        tick_state=_state(armed=False, status="BLOCKED_BROWSER"),
    )
    context = _context(service)
    context.start_rest_mode()
    assert context.automation_cycle_owner() == REST_MODE_OWNER

    result = context.tick_rest_mode(force=True)
    assert result.state.status == "BLOCKED_BROWSER"
    assert context.automation_cycle_owner() is None


def test_browser_driving_context_entries_fail_while_rest_mode_owns_authority() -> None:
    service = FakeRestMode(start_state=_state(armed=True, status="WATCHING"))
    context = _context(service)
    context.start_rest_mode()

    with pytest.raises(RuntimeError, match="owned by Rest Mode"):
        context.ensure_fleets_ready()
    with pytest.raises(RuntimeError, match="owned by Rest Mode"):
        context.process_spy("123", request_id="spy-1")
    with pytest.raises(RuntimeError, match="owned by Rest Mode"):
        context.step_discovery_scan("scan-1")
    with pytest.raises(RuntimeError, match="owned by Rest Mode"):
        context.dispatch_asteroid(
            source="3:39:11",
            observation=object(),
            recycler_count=5,
            request_id="asteroid-1",
        )
