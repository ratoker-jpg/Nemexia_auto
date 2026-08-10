from v2.infrastructure.cdp_rest_mode_reader import _ACTIVITY_RE


def test_activity_timer_requires_explicit_human_readable_minutes() -> None:
    match = _ACTIVITY_RE.search("Автоматический режим проверки через 176 мин.")
    assert match is not None
    assert int(match.group(1)) == 176


def test_raw_bot_check_or_template_is_not_treated_as_minutes() -> None:
    assert _ACTIVITY_RE.search("BOT_CHECK = 10050") is None
    assert _ACTIVITY_RE.search("Автоматический режим проверки через %1$s мин.") is None
    assert _ACTIVITY_RE.search("StringBotcheckTime = 'через 10050'") is None
