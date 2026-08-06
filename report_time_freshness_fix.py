from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import reports as reports_module
from browser import BrowserWorker
from models import utc_now


GAME_SERVER_TIMEZONE = timezone(timedelta(hours=4), name="UTC+04:00")
_ORIGINAL_IMPORT_REPORTS = BrowserWorker.import_reports
_INSTALLED = False


def _server_wall_clock_to_utc(value: datetime) -> datetime:
    """Interpret a naive Nemexia timestamp as server UTC+04 and store it in UTC."""
    wall_clock = value.replace(tzinfo=None)
    return wall_clock.replace(tzinfo=GAME_SERVER_TIMEZONE).astimezone(timezone.utc)


def _parse_report_date(node: Any) -> datetime | None:
    value = reports_module._text(node.select_one(".messageDate"))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return _server_wall_clock_to_utc(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


def _normalize_browser_report_times(reports):
    for report in reports:
        report_at = getattr(report, "report_at", None)
        if report_at is not None:
            # BrowserWorker.import_reports previously labelled the server wall clock as UTC.
            report.report_at = _server_wall_clock_to_utc(report_at)
    return reports


async def _import_reports_with_server_timezone(self: BrowserWorker, max_pages: int = 100):
    reports = await _ORIGINAL_IMPORT_REPORTS(self, max_pages=max_pages)
    return _normalize_browser_report_times(reports)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        # Legacy rows were written as UTC-naive/UTC-labelled values. Keep them comparable.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ranked_fresh_targets(self: Any, exclude_active: bool = True):
    active = self._active_coords() if exclude_active else set()
    minimum_metal = max(0, self._safe_int(self.min_metal_queue_var, 480000))
    max_age_hours = max(1, self._safe_int(self.report_lookback_var, 24))
    cutoff = utc_now() - timedelta(hours=max_age_hours)
    ranked = []
    for target in self.targets:
        spy_at = target.last_spy_at
        if (
            not target.enabled
            or target.blacklisted
            or target.coord in active
            or spy_at is None
            or _as_utc(spy_at) < cutoff
            or target.metal is None
            or target.metal < minimum_metal
        ):
            continue
        ranked.append((target, float(target.metal)))
    ranked.sort(key=lambda item: (-item[1], item[0].coord))
    return ranked


def install_report_time_freshness_fix(app_class: type[Any]) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    reports_module._date = _parse_report_date
    BrowserWorker.import_reports = _import_reports_with_server_timezone
    app_class.ranked_targets = _ranked_fresh_targets
    _INSTALLED = True
