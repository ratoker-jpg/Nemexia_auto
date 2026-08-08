from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from v2.application.spy_actions import (
    SpyActionError,
    SpyActionsDisabled,
    SpyActionService,
    SpyCaptchaBlocked,
    SpyRequestCommand,
    SpyRequestPreparation,
    SpyRequestResult,
)


class FakeBackend:
    def __init__(self, *, captcha: bool = False, verified: bool = True) -> None:
        self.captcha = captcha
        self.verified = verified
        self.prepared = []
        self.requested = []
        self.closed = False

    def prepare(self, command):
        self.prepared.append(command)
        return SpyRequestPreparation(
            fleet_id=command.fleet_id,
            source="3:39:11",
            target="2:22:19",
            captcha_present=self.captcha,
        )

    def request(self, command, preparation):
        self.requested.append((command, preparation))
        return SpyRequestResult(
            fleet_id=command.fleet_id,
            source=preparation.source,
            target=preparation.target,
            requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
            verified=self.verified,
            report_id="report-77" if self.verified else None,
            report_at=datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc) if self.verified else None,
        )

    def close(self):
        self.closed = True


def test_spy_actions_fail_closed_by_default() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend)
    command = SpyRequestCommand("152272")
    with pytest.raises(SpyActionsDisabled):
        service.prepare(command)
    with pytest.raises(SpyActionsDisabled):
        service.request(command)
    assert backend.prepared == backend.requested == []


def test_enabled_boundary_uses_exact_fleet_and_observed_route() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend, enabled=True)
    prep = service.prepare(SpyRequestCommand(" 152272 "))
    assert prep.fleet_id == "152272"
    assert prep.source == "3:39:11"
    assert prep.target == "2:22:19"
    result = service.request(SpyRequestCommand("152272"))
    assert result.verified is True
    assert result.report_id == "report-77"
    assert len(backend.requested) == 1


@pytest.mark.parametrize("fleet_id", ["", "0", "-1", "abc", "12.2"])
def test_invalid_fleet_id_never_reaches_backend(fleet_id: str) -> None:
    backend = FakeBackend()
    service = SpyActionService(backend, enabled=True)
    with pytest.raises(SpyActionError):
        service.request(SpyRequestCommand(fleet_id))
    assert backend.prepared == backend.requested == []


def test_captcha_fails_before_request_side_effect() -> None:
    backend = FakeBackend(captcha=True)
    service = SpyActionService(backend, enabled=True)
    with pytest.raises(SpyCaptchaBlocked):
        service.request(SpyRequestCommand("152272"))
    assert len(backend.prepared) == 1
    assert backend.requested == []


def test_verified_result_requires_report_identity_and_aware_time() -> None:
    class Bad(FakeBackend):
        def request(self, command, preparation):
            return SpyRequestResult(
                fleet_id=command.fleet_id,
                source=preparation.source,
                target=preparation.target,
                requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
                verified=True,
            )
    with pytest.raises(SpyActionError, match="exact report identity"):
        SpyActionService(Bad(), enabled=True).request(SpyRequestCommand("152272"))


def test_gate_can_be_armed_and_disarmed() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend)
    service.set_enabled(True)
    assert service.prepare(SpyRequestCommand("152272")).target == "2:22:19"
    service.set_enabled(False)
    with pytest.raises(SpyActionsDisabled):
        service.prepare(SpyRequestCommand("152272"))


def test_close_propagates() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend, enabled=True)
    service.close()
    assert backend.closed is True


def test_application_contract_has_no_browser_implementation() -> None:
    source = (Path(__file__).resolve().parents[1] / "v2/application/spy_actions.py").read_text(encoding="utf-8")
    for forbidden in ("playwright", "connect_over_cdp", ".goto(", ".click(", "page.evaluate", "BrowserWorker"):
        assert forbidden not in source
