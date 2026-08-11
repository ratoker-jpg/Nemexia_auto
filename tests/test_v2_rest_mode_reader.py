import asyncio
from pathlib import Path
from types import SimpleNamespace

from v2.infrastructure.cdp_rest_mode_reader import (
    _ACTIVITY_RE,
    _evaluation_failure_detail,
    _is_bot_check_url,
    OwnedRestModeReadMixin,
)


ROOT = Path(__file__).resolve().parents[1]
READER = (ROOT / "v2/infrastructure/cdp_rest_mode_reader.py").read_text(encoding="utf-8")
SAVED_FLEETS = (ROOT / "saved_pages/2026-08-08_08-54-11-072/page.html").read_text(
    encoding="utf-8"
)


def test_activity_timer_requires_explicit_human_readable_minutes() -> None:
    match = _ACTIVITY_RE.search("Автоматический режим проверки через 176 мин.")
    assert match is not None
    assert int(match.group(1)) == 176


def test_raw_bot_check_or_template_is_not_treated_as_minutes() -> None:
    assert _ACTIVITY_RE.search("BOT_CHECK = 10050") is None
    assert _ACTIVITY_RE.search("Автоматический режим проверки через %1$s мин.") is None
    assert _ACTIVITY_RE.search("StringBotcheckTime = 'через 10050'") is None


def test_real_saved_fleets_page_proves_server_time_activity_surface() -> None:
    assert 'id="serverTimeDisplay"' in SAVED_FLEETS
    assert 'onmouseover="Tip(getServerTimeTooltip());"' in SAVED_FLEETS
    assert "StringBotcheckTime = 'Автоматический режим проверки через %1$s мин.'" in SAVED_FLEETS


def test_reader_uses_only_visible_proven_server_time_surface() -> None:
    assert "document.querySelector('#serverTimeDisplay')" in READER
    assert "getServerTimeTooltip" in READER
    assert "getBoundingClientRect" in READER
    assert "timerVisible" in READER
    assert "timer_hook" in READER
    assert "activity_tooltip" in READER
    assert "querySelectorAll('[title]" not in READER
    assert "[aria-label]" not in READER
    assert "data-original-title" not in READER


def test_bot_check_route_is_affirmative_captcha_without_planet_dom() -> None:
    assert _is_bot_check_url("https://game.ares.nemexia.com/bot_check.php?redir=%2Ffleets.php") is True
    assert _is_bot_check_url("https://game.ares.nemexia.com/fleets.php") is False

    class Reader(OwnedRestModeReadMixin):
        def __init__(self) -> None:
            self.identity_calls = 0

        async def _existing_bound_page(self):
            return SimpleNamespace(
                url="https://game.ares.nemexia.com/bot_check.php?redir=%2Ffleets.php"
            )

        async def _read_browser_identity(self):
            self.identity_calls += 1
            raise AssertionError("bot-check URL must be classified before identity DOM read")

    reader = Reader()
    result = asyncio.run(
        reader._read_rest_mode_observation(
            expected_server_host="game.ares.nemexia.com",
            expected_account_fingerprint="account-a",
            expected_planet_id="17",
            expected_coord="3:39:11",
        )
    )
    assert result.captcha_required is True
    assert "bot_check.php" in result.detail
    assert reader.identity_calls == 0


def test_evaluation_failure_retains_and_tags_browser_context_loss() -> None:
    raw = "Execution context was destroyed, most likely because of a navigation"
    detail = _evaluation_failure_detail(RuntimeError(raw))
    assert detail.startswith("Browser/session loss")
    assert raw in detail

    parser_bug = _evaluation_failure_detail(RuntimeError("ReferenceError: timerProbe is not defined"))
    assert parser_bug.startswith("Rest Mode observation evaluation failed")
    assert "Browser/session loss" not in parser_bug
