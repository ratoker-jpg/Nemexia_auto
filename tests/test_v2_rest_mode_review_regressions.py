from types import SimpleNamespace

from v2.application.rest_mode import RestModeReadError, RestModeService
from v2.persistence.database import V2Database
from v2.persistence.rest_mode import RestModeRepository


class _NavigationWithUnresolved:
    def unresolved(self):
        return (SimpleNamespace(request_id="nav-captcha-ambiguous", status="ambiguous"),)

    def observe(self):  # pragma: no cover - this regression exercises terminal classification only
        raise AssertionError("no browser observation expected")


class _NavigationClear:
    def unresolved(self):
        return ()

    def observe(self):  # pragma: no cover
        raise AssertionError("no browser observation expected")


class _UnusedReadiness:
    def ensure_fleets(self):  # pragma: no cover
        raise AssertionError("no readiness work expected")


class _UnusedBrowser:
    def read_rest_mode_observation(self, **_kwargs):  # pragma: no cover
        raise AssertionError("no browser read expected")


def _service(tmp_path, navigation):
    database = V2Database(tmp_path / "v2.sqlite3")
    service = RestModeService(
        repository=RestModeRepository(database),
        navigation=navigation,
        readiness=_UnusedReadiness(),
        browser=_UnusedBrowser(),
    )
    return database, service


def test_captcha_status_precedes_navigation_ambiguity_but_keeps_request_evidence(tmp_path) -> None:
    database, service = _service(tmp_path, _NavigationWithUnresolved())

    state = service._block_for_exception(
        RuntimeError("CAPTCHA = STOP after ambiguous fleets.php preparation")
    )

    assert state.armed is False
    assert state.status == "CAPTCHA_REQUIRED"
    assert state.blocking_navigation_request_id == "nav-captcha-ambiguous"
    assert "CAPTCHA" in state.last_error
    database.close()


def test_incidental_raw_bot_check_diagnostic_remains_parser_error_not_captcha(tmp_path) -> None:
    database, service = _service(tmp_path, _NavigationClear())

    state = service._block_for_exception(
        RestModeReadError(
            "Activity timer is malformed; raw BOT_CHECK units are intentionally ignored"
        )
    )

    assert state.armed is False
    assert state.status == "ERROR"
    assert state.blocking_navigation_request_id == ""
    assert "BOT_CHECK" in state.last_error
    database.close()
