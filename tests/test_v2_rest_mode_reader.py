from pathlib import Path

from v2.infrastructure.cdp_rest_mode_reader import _ACTIVITY_RE


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
