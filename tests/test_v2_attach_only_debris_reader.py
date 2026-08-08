from __future__ import annotations

import inspect
from datetime import datetime, timezone

from v2.application.debris_source import V2DebrisSource
from v2.domain.debris import DebrisReadState
from v2.infrastructure.cdp_asteroid_reader import ReadOnlyAsteroidCdpBackend
from v2.infrastructure.cdp_debris_reader import ReadOnlyDebrisCdpBackend, snapshot_from_raw


READY = """
<div>Информация об астероиде</div>
<div>Последнее перемещение 2026-08-06 20:45:08</div>
<div>Следующее перемещение 2026-08-06 21:46:08</div>
<div>Скорость 61 Минут / поле</div>
<div>Этот астероид содержит обломки</div>
"""
PLAIN = READY.replace("<div>Этот астероид содержит обломки</div>", "")
PARTIAL = "<div>Информация об астероиде</div><div>Этот астероид содержит обломки</div>"


class FakeBackend:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def read_debris(self):
        return self.snapshot


def test_current_system_raw_maps_debris_and_reuses_asteroid_provenance() -> None:
    snapshot = snapshot_from_raw(
        {
            "page_url": "https://game.ares.nemexia.com/galaxy.php?galaxy=2&solar=23",
            "server_time": [2026, 8, 6, 20, 57, 38],
            "asteroids": [
                {"g": 2, "s": 23, "p": 8, "tooltip": READY},
                {"g": 2, "s": 23, "p": 9, "tooltip": PLAIN},
            ],
        }
    )
    assert snapshot.visible_asteroids == 2
    assert snapshot.readable_square_info == 2
    assert len(snapshot.observations) == 1
    fact = snapshot.observations[0]
    assert fact.coord == "2:23:8"
    assert fact.asteroid.observed_at == datetime(2026, 8, 6, 16, 57, 38, tzinfo=timezone.utc)
    read = V2DebrisSource(FakeBackend(snapshot)).read()
    assert read.state is DebrisReadState.READY
    assert read.complete_current_system_evidence


def test_partial_square_info_stays_partial_even_when_another_debris_is_proven() -> None:
    snapshot = snapshot_from_raw(
        {
            "server_time": [2026, 8, 6, 20, 57, 38],
            "asteroids": [
                {"g": 1, "s": 40, "p": 1, "tooltip": READY},
                {"g": 1, "s": 40, "p": 2, "tooltip": PARTIAL},
            ],
        }
    )
    assert snapshot.visible_asteroids == 2
    assert snapshot.readable_square_info == 1
    assert len(snapshot.observations) == 1
    read = V2DebrisSource(FakeBackend(snapshot)).read()
    assert read.state is DebrisReadState.PARTIAL_EVIDENCE
    assert not read.complete_current_system_evidence


def test_fully_readable_zero_debris_is_current_system_no_debris() -> None:
    snapshot = snapshot_from_raw(
        {
            "server_time": [2026, 8, 6, 20, 57, 38],
            "asteroids": [{"g": 3, "s": 7, "p": 3, "tooltip": PLAIN}],
        }
    )
    read = V2DebrisSource(FakeBackend(snapshot)).read()
    assert read.state is DebrisReadState.NO_DEBRIS
    assert read.observations == ()
    assert read.complete_current_system_evidence


def test_empty_current_system_is_no_debris_not_full_scan_claim() -> None:
    snapshot = snapshot_from_raw(
        {"server_time": [2026, 8, 6, 20, 57, 38], "asteroids": []}
    )
    read = V2DebrisSource(FakeBackend(snapshot)).read()
    assert read.state is DebrisReadState.NO_DEBRIS
    assert "120" not in read.detail


def test_debris_reader_inherits_only_the_attach_only_asteroid_read_boundary() -> None:
    assert issubclass(ReadOnlyDebrisCdpBackend, ReadOnlyAsteroidCdpBackend)
    source = inspect.getsource(ReadOnlyDebrisCdpBackend) + inspect.getsource(ReadOnlyAsteroidCdpBackend)
    for token in (
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "_select_planet(",
        ".click(",
        "SendFleet",
        "ajax_galaxy.php",
    ):
        assert token not in source
    assert "_read_current_galaxy" in source
    assert "fetch('ajax_info.php'" in source
    assert "type:'squareInfo'" in source
