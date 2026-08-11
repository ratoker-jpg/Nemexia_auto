from datetime import datetime, timezone
from types import SimpleNamespace

from v2.application.browser_identity import PlanetDomFact, build_browser_identity
from v2.application.navigation import NavigationObservation, NavigationPageState
from v2.application.rest_mode import (
    RestModeObservation,
    RestModeReadError,
    RestModeService,
)
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


def _verified_fleets_observation() -> NavigationObservation:
    identity = build_browser_identity(
        endpoint="http://127.0.0.1:9222",
        page_url="https://game.ares.nemexia.com/fleets.php",
        page_count=1,
        game_page_count=1,
        planets=(
            PlanetDomFact(
                planet_id="17",
                coord="3:39:11",
                display_name="Home",
                selected_by_list=True,
            ),
        ),
        trigger_coord="3:39:11",
    )
    return NavigationObservation(
        page_token="page-1",
        identity=identity,
        page=NavigationPageState(page_kind="fleets", fleets_ready=True),
    )


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


def test_reader_captcha_is_persisted_before_final_identity_observation(tmp_path) -> None:
    verified = _verified_fleets_observation()

    class Navigation:
        def __init__(self) -> None:
            self.observe_calls = 0

        def unresolved(self):
            return ()

        def observe(self):
            self.observe_calls += 1
            if self.observe_calls <= 3:
                return verified
            raise AssertionError(
                "final identity observation must not run after positive CAPTCHA evidence"
            )

    class Readiness:
        def __init__(self) -> None:
            self.calls = 0

        def ensure_fleets(self):
            self.calls += 1
            return object()

    class Browser:
        def __init__(self) -> None:
            self.calls = 0

        def read_rest_mode_observation(self, **_kwargs):
            self.calls += 1
            return RestModeObservation(
                observed_at=datetime(2026, 8, 11, 21, 30, tzinfo=timezone.utc).isoformat(),
                activity_minutes=0,
                captcha_required=True,
                detail="CAPTCHA / bot-check detected from coordinator-owned bot_check.php URL",
            )

    database = V2Database(tmp_path / "captcha.sqlite3")
    navigation = Navigation()
    readiness = Readiness()
    browser = Browser()
    service = RestModeService(
        repository=RestModeRepository(database),
        navigation=navigation,
        readiness=readiness,
        browser=browser,
    )

    result = service.start(
        now=datetime(2026, 8, 11, 21, 30, tzinfo=timezone.utc)
    )

    assert result.state.armed is False
    assert result.state.status == "CAPTCHA_REQUIRED"
    assert navigation.observe_calls == 3  # initial Start + before + after readiness
    assert readiness.calls == 1
    assert browser.calls == 1
    database.close()
