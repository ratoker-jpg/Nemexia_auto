from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from v2.application.asteroid_autorenew_context import AsteroidAutorenewApplicationContext
from v2.application.asteroid_repository import V2AsteroidRepository
from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness
from v2.infrastructure.qt_autorenew_driver import QtAsteroidAutorenewDriver
from v2.persistence.asteroid_autorenew import AsteroidAutorenewRepository
from v2.persistence.asteroid_candidates import AsteroidObservationRepository
from v2.persistence.database import V2Database, V2DatabaseError
from v2.persistence.discovery_scan import DiscoveryScanRepository


ROOT = Path(__file__).resolve().parents[1]


class _Signal:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback) -> None:
        self.callback = callback


class _Timer:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.interval = None
        self.running = False
        self.timeout = _Signal()

    def setInterval(self, value: int) -> None:
        self.interval = int(value)

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


def _install_fake_qt(monkeypatch) -> None:
    pyside = ModuleType("PySide6")
    qtcore = ModuleType("PySide6.QtCore")
    qtcore.QTimer = _Timer
    pyside.QtCore = qtcore
    monkeypatch.setitem(sys.modules, "PySide6", pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)


def _arm_repository(repo: AsteroidAutorenewRepository, *, session_id: str) -> None:
    repo.arm(
        session_id=session_id,
        source_planet_id="101",
        source_coord="3:39:8",
        account_fingerprint="acct",
        recycler_count=5,
        max_flights=15,
        safety_seconds=10,
        buffer_minutes=5,
    )


def test_qt_driver_ticks_only_armed_scheduler_and_is_wired_to_main_window(monkeypatch) -> None:
    _install_fake_qt(monkeypatch)

    class Context:
        def __init__(self) -> None:
            self.armed = False
            self.ticks = 0
            self.stops: list[str] = []

        def asteroid_autorenew_state(self):
            return SimpleNamespace(armed=self.armed)

        def tick_asteroid_autorenew(self):
            self.ticks += 1

        def stop_asteroid_autorenew(self, *, detail: str):
            self.stops.append(detail)

    context = Context()
    driver = QtAsteroidAutorenewDriver(context, interval_ms=1000)
    assert driver.timer.interval == 1000

    driver.start()
    assert driver.timer.running is True
    driver._tick()
    assert context.ticks == 0

    context.armed = True
    driver._tick()
    assert context.ticks == 1

    driver.stop()
    assert driver.timer.running is False

    main_window = (ROOT / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "QtAsteroidAutorenewDriver(context, parent=window)" in main_window
    assert "autorenew_driver.start()" in main_window
    assert "app.aboutToQuit.connect(autorenew_driver.stop)" in main_window


def test_qt_driver_disarms_after_tick_exception(monkeypatch) -> None:
    _install_fake_qt(monkeypatch)

    class Context:
        def __init__(self) -> None:
            self.stop_detail = ""

        def asteroid_autorenew_state(self):
            return SimpleNamespace(armed=True)

        def tick_asteroid_autorenew(self):
            raise RuntimeError("boom")

        def stop_asteroid_autorenew(self, *, detail: str):
            self.stop_detail = detail

    context = Context()
    driver = QtAsteroidAutorenewDriver(context)
    driver._tick()
    assert "Qt autorenew driver stopped after error: boom" == context.stop_detail


def test_context_close_uses_service_stop_before_parent_close(monkeypatch) -> None:
    calls: list[str] = []

    class Service:
        def state(self):
            return SimpleNamespace(armed=True)

        def stop(self, *, detail: str):
            calls.append(f"service:{detail}")

    monkeypatch.setattr(
        DebrisEnabledApplicationContextWithReadiness,
        "close",
        lambda self: calls.append("parent-close"),
    )
    context = object.__new__(AsteroidAutorenewApplicationContext)
    context._asteroid_autorenew = Service()

    context.close()

    assert calls[0].startswith("service:Application closed")
    assert calls[1] == "parent-close"
    assert context._asteroid_autorenew is None


def test_scan_provenance_excludes_parallel_manual_observation(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    storage = AsteroidObservationRepository(database)
    observation_ids = storage.ensure_with_ids(
        [
            {
                "galaxy": 1,
                "system": 40,
                "position": 3,
                "last_move_at": "2026-08-09T16:00:00+00:00",
                "next_move_at": "2026-08-09T17:00:00+00:00",
                "period_seconds": 3600,
                "observed_at": "2026-08-09T16:30:00+00:00",
                "source": "galaxy.squareInfo",
            },
            {
                "galaxy": 2,
                "system": 10,
                "position": 7,
                "last_move_at": "2026-08-09T16:05:00+00:00",
                "next_move_at": "2026-08-09T17:05:00+00:00",
                "period_seconds": 3600,
                "observed_at": "2026-08-09T16:35:00+00:00",
                "source": "manual.current-system",
            },
        ]
    )
    assert len(observation_ids) == 2

    autorenew = AsteroidAutorenewRepository(database)
    autorenew.record_scan_observations(
        scan_id="scan-owned",
        sequence_index=0,
        observation_ids=(observation_ids[0],),
    )

    scoped_ids = autorenew.scan_observation_ids("scan-owned")
    assert scoped_ids == (observation_ids[0],)
    facts = V2AsteroidRepository(database).observations_by_ids(scoped_ids)
    assert len(facts) == 1
    assert (facts[0].galaxy, facts[0].system, facts[0].position) == (1, 40, 3)
    assert observation_ids[1] not in scoped_ids
    database.close()


def test_internal_stop_preserves_ambiguous_discovery_identity_and_blocks_new_start(tmp_path: Path) -> None:
    database = V2Database(tmp_path / "v2.sqlite3")
    autorenew = AsteroidAutorenewRepository(database)
    discovery = DiscoveryScanRepository(database)
    _arm_repository(autorenew, session_id="session-ambiguous")
    scan = discovery.begin(
        scan_id="scan-ambiguous",
        account_fingerprint="acct",
        planet_id="101",
        planet_coord="3:39:8",
    )
    autorenew.transition(
        status="running_discovery",
        armed=True,
        active_scan_id=scan.scan_id,
        detail="running",
    )
    discovery.finish_safe(
        scan.scan_id,
        status="ambiguous",
        detail="navigation effect unresolved",
    )

    stopped = autorenew.stop(status="stopped_ambiguous", detail="navigation ambiguous")
    assert stopped.armed is False
    assert stopped.active_scan_id == scan.scan_id
    assert "unresolved discovery scan preserved" in stopped.detail

    with pytest.raises(V2DatabaseError, match="scan-ambiguous"):
        _arm_repository(autorenew, session_id="session-must-not-start")
    assert autorenew.read().active_scan_id == scan.scan_id
    assert discovery.read(scan.scan_id).status == "ambiguous"
    database.close()


def test_restart_disarm_retains_running_discovery_recovery_identity(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    database = V2Database(path)
    autorenew = AsteroidAutorenewRepository(database)
    discovery = DiscoveryScanRepository(database)
    _arm_repository(autorenew, session_id="session-crash")
    scan = discovery.begin(
        scan_id="scan-crash",
        account_fingerprint="acct",
        planet_id="101",
        planet_coord="3:39:8",
    )
    autorenew.transition(
        status="running_discovery",
        armed=True,
        active_scan_id=scan.scan_id,
        detail="running before crash",
    )
    database.close()

    reopened = V2Database(path)
    recovered_repo = AsteroidAutorenewRepository(reopened)
    recovered = recovered_repo.disarm_on_startup()
    assert recovered.armed is False
    assert recovered.status == "disarmed_restart"
    assert recovered.active_scan_id == scan.scan_id
    assert "unresolved discovery scan preserved" in recovered.detail
    with pytest.raises(V2DatabaseError, match="scan-crash"):
        _arm_repository(recovered_repo, session_id="session-after-crash")
    reopened.close()
