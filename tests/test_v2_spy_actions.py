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
    def __init__(
        self,
        *,
        available: int = 20,
        ship_key: str = "spy_probe",
        captcha: bool = False,
        verified: bool = True,
    ) -> None:
        self.available = available
        self.ship_key = ship_key
        self.captcha = captcha
        self.verified = verified
        self.prepared: list[SpyRequestCommand] = []
        self.requested: list[tuple[SpyRequestCommand, SpyRequestPreparation]] = []
        self.closed = False

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        self.prepared.append(command)
        return SpyRequestPreparation(
            source=command.source,
            target=command.target,
            probe_count=command.probe_count,
            probe_ship_key=self.ship_key,
            available_probes=self.available,
            captcha_present=self.captcha,
            detail="CAPTCHA" if self.captcha else "ready",
        )

    def request(
        self,
        command: SpyRequestCommand,
        preparation: SpyRequestPreparation,
    ) -> SpyRequestResult:
        self.requested.append((command, preparation))
        return SpyRequestResult(
            source=command.source,
            target=command.target,
            probe_count=command.probe_count,
            requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
            verified=self.verified,
            report_id="report-77" if self.verified else None,
            report_at=(
                datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc)
                if self.verified
                else None
            ),
        )

    def close(self) -> None:
        self.closed = True


def test_spy_actions_are_fail_closed_by_default() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend)
    command = SpyRequestCommand("3:39:11", "3:1:2", 5)
    with pytest.raises(SpyActionsDisabled):
        service.prepare(command)
    with pytest.raises(SpyActionsDisabled):
        service.request(command)
    assert backend.prepared == []
    assert backend.requested == []


def test_enabled_boundary_normalizes_and_validates_before_backend() -> None:
    backend = FakeBackend(available=12)
    service = SpyActionService(backend, enabled=True)
    preparation = service.prepare(SpyRequestCommand(" 3 : 39 : 11 ", " 3 : 1 : 2 ", 5))
    assert preparation.source == "3:39:11"
    assert preparation.target == "3:1:2"
    assert preparation.probe_ship_key == "spy_probe"
    assert preparation.available_probes == 12
    assert backend.prepared == [SpyRequestCommand("3:39:11", "3:1:2", 5)]

    result = service.request(SpyRequestCommand("3:39:11", "3:1:2", 5))
    assert result.verified is True
    assert result.report_id == "report-77"
    assert len(backend.requested) == 1
    assert backend.requested[0][0] == SpyRequestCommand("3:39:11", "3:1:2", 5)


@pytest.mark.parametrize(
    "command",
    [
        SpyRequestCommand("bad", "3:1:2", 5),
        SpyRequestCommand("3:39:11", "bad", 5),
        SpyRequestCommand("3:39:11", "3:1:2", 0),
        SpyRequestCommand("3:39:11", "3:39:11", 5),
        SpyRequestCommand("0:39:11", "3:1:2", 5),
    ],
)
def test_invalid_commands_never_reach_backend(command: SpyRequestCommand) -> None:
    backend = FakeBackend()
    service = SpyActionService(backend, enabled=True)
    with pytest.raises(SpyActionError):
        service.request(command)
    assert backend.prepared == []
    assert backend.requested == []


def test_probe_facts_fail_closed_before_request_side_effect() -> None:
    insufficient = FakeBackend(available=4)
    service = SpyActionService(insufficient, enabled=True)
    with pytest.raises(SpyActionError, match="Insufficient probes"):
        service.request(SpyRequestCommand("3:39:11", "3:1:2", 5))
    assert insufficient.requested == []

    unidentified = FakeBackend(ship_key="")
    service = SpyActionService(unidentified, enabled=True)
    with pytest.raises(SpyActionError, match="identify"):
        service.request(SpyRequestCommand("3:39:11", "3:1:2", 5))
    assert unidentified.requested == []


def test_captcha_fails_closed_before_request_side_effect() -> None:
    backend = FakeBackend(captcha=True)
    service = SpyActionService(backend, enabled=True)
    with pytest.raises(SpyCaptchaBlocked):
        service.request(SpyRequestCommand("3:39:11", "3:1:2", 5))
    assert len(backend.prepared) == 1
    assert backend.requested == []


def test_verified_result_requires_exact_report_identity_and_aware_time() -> None:
    class BadResultBackend(FakeBackend):
        def request(self, command, preparation):
            return SpyRequestResult(
                source=command.source,
                target=command.target,
                probe_count=command.probe_count,
                requested_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
                verified=True,
                report_id=None,
                report_at=None,
            )

    service = SpyActionService(BadResultBackend(), enabled=True)
    with pytest.raises(SpyActionError, match="exact report identity"):
        service.request(SpyRequestCommand("3:39:11", "3:1:2", 5))


def test_action_gate_can_be_explicitly_armed_and_disarmed() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend)
    service.set_enabled(True)
    assert service.prepare(SpyRequestCommand("3:39:11", "3:1:2", 5)).available_probes == 20
    service.set_enabled(False)
    with pytest.raises(SpyActionsDisabled):
        service.prepare(SpyRequestCommand("3:39:11", "3:1:2", 5))


def test_close_propagates_to_backend() -> None:
    backend = FakeBackend()
    service = SpyActionService(backend, enabled=True)
    service.close()
    assert backend.closed is True


def test_spy_action_contract_has_no_browser_or_game_send_implementation() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "application" / "spy_actions.py").read_text(encoding="utf-8")
    for forbidden in (
        "playwright",
        "connect_over_cdp",
        "processSpy",
        "ajax_fleets.php",
        ".click(",
        ".goto(",
        "page.evaluate",
        "BrowserWorker",
        "delete_messages",
    ):
        assert forbidden not in source
