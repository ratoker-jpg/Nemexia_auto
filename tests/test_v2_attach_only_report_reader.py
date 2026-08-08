from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from v2.infrastructure.spy_report_parser import parse_rendered_spy_reports


FIXTURE = Path(__file__).parent / "fixtures" / "v2_spy_report_contract.html"


def test_v2_parser_reads_rendered_report_identity_target_time_and_resources() -> None:
    reports = parse_rendered_spy_reports(FIXTURE.read_text(encoding="utf-8"))
    assert len(reports) == 2
    first, second = reports
    assert first.report_id == "audit-101"
    assert first.target == "3:39:11"
    assert first.reported_at == datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    assert (first.energy, first.metal, first.minerals, first.gas) == (7000, 600_000, 520_000, 10_000)
    assert first.source == "browser:TabAdministrative"
    assert second.report_id == "audit-102"
    assert second.target == "3:38:9"
    assert second.reported_at == datetime(2026, 8, 7, 6, 0, tzinfo=timezone.utc)


def test_report_reader_is_strictly_attach_only() -> None:
    root = Path(__file__).resolve().parents[1]
    adapter = (root / "v2" / "infrastructure" / "cdp_account_reader.py").read_text(encoding="utf-8")
    parser = (root / "v2" / "infrastructure" / "spy_report_parser.py").read_text(encoding="utf-8")
    service = (root / "v2" / "application" / "report_source.py").read_text(encoding="utf-8")

    assert "options.php" in adapter
    assert "#TabAdministrativeBox" in adapter
    assert "#messagesList" in adapter
    assert "connect_over_cdp" not in adapter  # inherited CDP attachment only
    for forbidden in (
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "bring_to_front(",
        "loadTabContent",
        "processSpy",
        "ajax_messages.php",
        "deleteSelectedMessages",
        "deleteAllMessages",
        "BrowserWorker",
        "launch_yandex",
    ):
        assert forbidden not in adapter
        assert forbidden not in parser
        assert forbidden not in service


def test_report_parser_never_invents_missing_timestamp_or_target() -> None:
    html = """
    <div class='messageItem'>
      <div class='messageBody' id='body-undated'><b>Шпионский отчет 3:1:2</b></div>
      <input name='messageSelect[undated]' value='undated'>
    </div>
    <div class='messageItem'>
      <div class='messageDate'>2026-08-08 14:00:00</div>
      <div class='messageBody' id='body-no-target'><b>Шпионский отчет</b></div>
    </div>
    """
    reports = parse_rendered_spy_reports(html)
    assert len(reports) == 1
    assert reports[0].report_id == "undated"
    assert reports[0].target == "3:1:2"
    assert reports[0].reported_at is None
