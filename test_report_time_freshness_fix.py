from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from models import utc_now
from report_time_freshness_fix import (
    _normalize_browser_report_times,
    _ranked_fresh_targets,
    _server_wall_clock_to_utc,
)


class FakeApp:
    def __init__(self, targets):
        self.targets = targets
        self.min_metal_queue_var = 480000
        self.report_lookback_var = 24

    def _active_coords(self):
        return set()

    @staticmethod
    def _safe_int(value, fallback):
        try:
            return int(value)
        except Exception:
            return fallback


class ReportTimeFreshnessFixTest(unittest.TestCase):
    def test_server_utc_plus_four_is_converted_to_utc(self) -> None:
        wall_clock = datetime(2026, 8, 6, 20, 15, 0)
        converted = _server_wall_clock_to_utc(wall_clock)
        self.assertEqual(converted, datetime(2026, 8, 6, 16, 15, 0, tzinfo=timezone.utc))

    def test_browser_import_repairs_wrongly_labelled_utc(self) -> None:
        report = SimpleNamespace(report_at=datetime(2026, 8, 6, 20, 15, 0, tzinfo=timezone.utc))
        _normalize_browser_report_times([report])
        self.assertEqual(report.report_at.hour, 16)
        self.assertEqual(report.report_at.tzinfo, timezone.utc)

    def test_stale_recon_is_excluded_but_fresh_order_stays_by_metal(self) -> None:
        now = utc_now()
        stale = SimpleNamespace(
            coord="3:1:1", enabled=True, blacklisted=False,
            last_spy_at=now - timedelta(hours=25), metal=900000,
        )
        fresh_low = SimpleNamespace(
            coord="3:1:2", enabled=True, blacklisted=False,
            last_spy_at=now - timedelta(hours=2), metal=500000,
        )
        fresh_high = SimpleNamespace(
            coord="3:1:3", enabled=True, blacklisted=False,
            last_spy_at=now - timedelta(minutes=10), metal=800000,
        )
        ranked = _ranked_fresh_targets(FakeApp([stale, fresh_low, fresh_high]))
        self.assertEqual([target.coord for target, _ in ranked], ["3:1:3", "3:1:2"])


if __name__ == "__main__":
    unittest.main()
