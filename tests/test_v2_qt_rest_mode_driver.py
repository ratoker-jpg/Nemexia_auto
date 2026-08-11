from __future__ import annotations

from datetime import datetime, timezone

from v2.application.rest_mode import RestModeCycleResult
from v2.infrastructure.qt_rest_mode_driver import QtRestModeDriver
from v2.persistence.rest_mode import REST_MODE_ATTACK_UNVERIFIED, RestModeState


NOW = datetime(2026, 8, 11, 21, 40, tzinfo=timezone.utc).isoformat()


def _state(
    *,
    status: str,
    armed: bool,
    account: str = "account-a",
    planet_id: str = "17",
    coord: str = "3:39:11",
    epoch: int = 0,
    minutes: int | None = None,
    warning_sent: bool = False,
    detail: str = "",
) -> RestModeState:
    return RestModeState(
        armed=armed,
        status=status,
        session_id="rest-mode:test",
        server_host="game.ares.nemexia.com",
        account_fingerprint=account,
        planet_id=planet_id,
        planet_coord=coord,
        started_at=NOW,
        last_success_at=NOW if minutes is not None else None,
        next_check_at=NOW if armed else None,
        last_activity_minutes=minutes,
        activity_epoch=epoch,
        activity_warning_sent=warning_sent,
        attack_watch_state=REST_MODE_ATTACK_UNVERIFIED,
        last_error=detail,
        blocking_navigation_request_id="",
        detail=detail,
        updated_at=NOW,
    )


def _driver(context, notices):
    driver = object.__new__(QtRestModeDriver)
    driver.context = context
    driver.notify = lambda title, message: notices.append((title, message))
    driver._last_activity_notice_key = ""
    driver._last_terminal_notice_key = ""
    driver._last_driver_notice_key = ""
    return driver


def test_immediate_terminal_start_result_notifies_without_scheduler_tick() -> None:
    terminal = _state(
        status="CAPTCHA_REQUIRED",
        armed=False,
        detail="CAPTCHA / bot-check detected",
    )

    class Context:
        tick_calls = 0

        def rest_mode_state(self):
            return terminal

        def tick_rest_mode(self):
            self.tick_calls += 1
            raise AssertionError("disarmed terminal Start result must not schedule a tick")

    context = Context()
    notices = []
    driver = _driver(context, notices)

    driver._tick()
    driver._tick()

    assert context.tick_calls == 0
    assert len(notices) == 1
    assert notices[0][0] == "Nemexia · Rest Mode остановлен"
    assert "CAPTCHA" in notices[0][1]


def test_first_low_start_result_notifies_even_when_followup_tick_emits_no_new_warning() -> None:
    warning = _state(
        status="ACTIVITY_WARNING",
        armed=True,
        epoch=0,
        minutes=20,
        warning_sent=True,
    )

    class Context:
        tick_calls = 0

        def rest_mode_state(self):
            return warning

        def tick_rest_mode(self):
            self.tick_calls += 1
            return RestModeCycleResult(warning, warning_emitted=False)

    context = Context()
    notices = []
    driver = _driver(context, notices)

    driver._tick()
    driver._tick()

    assert context.tick_calls == 2
    assert len(notices) == 1
    assert "20 мин." in notices[0][1]


def test_activity_notice_dedupe_is_scoped_to_verified_identity_and_epoch() -> None:
    notices = []
    driver = _driver(object(), notices)
    first = _state(
        status="ACTIVITY_WARNING",
        armed=True,
        account="account-a",
        planet_id="17",
        coord="3:39:11",
        epoch=0,
        minutes=20,
        warning_sent=True,
    )
    same_epoch_same_identity = _state(
        status="ACTIVITY_WARNING",
        armed=True,
        account="account-a",
        planet_id="17",
        coord="3:39:11",
        epoch=0,
        minutes=15,
        warning_sent=True,
    )
    different_identity_same_epoch = _state(
        status="ACTIVITY_WARNING",
        armed=True,
        account="account-b",
        planet_id="44",
        coord="2:10:4",
        epoch=0,
        minutes=20,
        warning_sent=True,
    )

    driver._notify_state(first)
    driver._notify_state(same_epoch_same_identity)
    driver._notify_state(different_identity_same_epoch)

    assert len(notices) == 2
    assert "20 мин." in notices[0][1]
    assert "20 мин." in notices[1][1]


def test_terminal_notice_does_not_erase_activity_epoch_dedupe() -> None:
    notices = []
    driver = _driver(object(), notices)
    warning = _state(
        status="ACTIVITY_WARNING",
        armed=True,
        epoch=3,
        minutes=20,
        warning_sent=True,
    )
    blocked = _state(
        status="BLOCKED_BROWSER",
        armed=False,
        epoch=3,
        minutes=20,
        warning_sent=True,
        detail="Browser/session loss",
    )

    driver._notify_state(warning)
    driver._notify_state(blocked)
    driver._notify_state(warning)

    assert len(notices) == 2
    assert notices[0][0] == "Nemexia · проверка активности"
    assert notices[1][0] == "Nemexia · Rest Mode остановлен"
