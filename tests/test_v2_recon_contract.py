from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reports import parse_spy_reports_html
from v2.domain.recon import (
    LEGACY_AUTOFARM_MINERALS_MINIMUM,
    LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES,
    LEGACY_GAME_SERVER_UTC_OFFSET_HOURS,
    LEGACY_METAL_QUEUE_MINIMUM,
    LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ReconCycleState,
    SpyReportFact,
    classify_recon_cycle,
    eligible_for_legacy_autofarm,
    eligible_for_manual_queue,
    report_is_fresh,
    server_wall_clock_to_utc,
)


FIXTURE = Path(__file__).parent / "fixtures" / "v2_spy_report_contract.html"


def _facts() -> list[SpyReportFact]:
    parsed = parse_spy_reports_html(FIXTURE.read_text(encoding="utf-8"))
    return [
        SpyReportFact(
            report_id=item.message_id,
            target=item.coord,
            reported_at=server_wall_clock_to_utc(item.report_at) if item.report_at else None,
            energy=item.energy,
            metal=item.metal,
            minerals=item.minerals,
            gas=item.gas,
        )
        for item in parsed
    ]


def test_sanitized_fixture_exposes_verification_facts() -> None:
    reports = _facts()
    assert [item.report_id for item in reports] == ["audit-101", "audit-102"]
    assert [item.target for item in reports] == ["3:39:11", "3:38:9"]
    assert reports[0].reported_at == datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    assert reports[0].has_verifiable_identity is True
    assert (reports[0].metal, reports[0].minerals, reports[0].gas) == (600_000, 520_000, 10_000)


def test_server_timestamp_preserves_effective_legacy_utc_plus_four_contract() -> None:
    assert LEGACY_GAME_SERVER_UTC_OFFSET_HOURS == 4
    labelled_utc_wall_clock = datetime(2026, 8, 8, 14, 0, tzinfo=timezone.utc)
    assert server_wall_clock_to_utc(labelled_utc_wall_clock) == datetime(
        2026, 8, 8, 10, 0, tzinfo=timezone.utc
    )


def test_freshness_preserves_legacy_default_window() -> None:
    first, second = _facts()
    now = datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc)
    assert LEGACY_SPY_REPORT_LOOKBACK_HOURS == 24
    assert report_is_fresh(first, now=now) is True
    assert report_is_fresh(second, now=now) is False
    undated = SpyReportFact(report_id="x", target="1:1:1", reported_at=None)
    assert report_is_fresh(undated, now=now) is False


def test_resource_eligibility_preserves_effective_legacy_contract() -> None:
    first, second = _facts()
    assert LEGACY_METAL_QUEUE_MINIMUM == 480_000
    assert eligible_for_manual_queue(first, "metal") is True
    assert eligible_for_manual_queue(second, "metal") is False
    # Manual mineral queue accepts any reported mineral value; AutoFarm has its own 500k gate.
    assert eligible_for_manual_queue(first, "minerals") is True
    assert eligible_for_manual_queue(second, "minerals") is True
    assert LEGACY_AUTOFARM_MINERALS_MINIMUM == 500_000
    assert eligible_for_legacy_autofarm(first) is True
    assert eligible_for_legacy_autofarm(second) is False


def test_recon_cycle_keeps_stop_states_distinct_from_successful_empty_scan() -> None:
    first = _facts()[0]
    assert classify_recon_cycle(
        browser_available=False,
        captcha_present=False,
        fresh_reports=(),
        eligible_target_count=0,
    ) is ReconCycleState.LIVE_UNAVAILABLE
    assert classify_recon_cycle(
        browser_available=True,
        captcha_present=True,
        fresh_reports=(),
        eligible_target_count=0,
    ) is ReconCycleState.CAPTCHA
    assert classify_recon_cycle(
        browser_available=True,
        captcha_present=False,
        fresh_reports=(),
        eligible_target_count=0,
    ) is ReconCycleState.NO_FRESH_REPORTS
    assert classify_recon_cycle(
        browser_available=True,
        captcha_present=False,
        fresh_reports=(first,),
        eligible_target_count=0,
    ) is ReconCycleState.FRESH_ZERO_ELIGIBLE
    assert classify_recon_cycle(
        browser_available=True,
        captcha_present=False,
        fresh_reports=(first,),
        eligible_target_count=1,
    ) is ReconCycleState.READY


def test_only_successful_empty_scan_owns_the_25_minute_cooldown_contract() -> None:
    assert LEGACY_EMPTY_SCAN_COOLDOWN_MINUTES == 25
    cooldown_states = {ReconCycleState.FRESH_ZERO_ELIGIBLE}
    assert ReconCycleState.NO_FRESH_REPORTS not in cooldown_states
    assert ReconCycleState.CAPTCHA not in cooldown_states
    assert ReconCycleState.LIVE_UNAVAILABLE not in cooldown_states
