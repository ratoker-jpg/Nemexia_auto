from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from v2.infrastructure.cdp_asteroid_reader import (
    AsteroidReadError,
    ReadOnlyAsteroidCdpBackend,
    observations_from_raw,
)


TOOLTIP = """
<div>Информация об астероиде</div>
<div>Последнее перемещение 2026-08-06 20:45:08</div>
<div>Следующее перемещение 2026-08-06 21:46:08</div>
<div>Скорость 61 Минут / поле</div>
"""


def test_raw_current_system_maps_to_observations_and_deduplicates() -> None:
    raw = {
        "server_time": [2026, 8, 6, 20, 57, 38],
        "asteroids": [
            {"g": 2, "s": 23, "p": 8, "tooltip": TOOLTIP},
            {"g": 2, "s": 23, "p": 8, "tooltip": TOOLTIP},
        ],
    }
    observations = observations_from_raw(raw)
    assert len(observations) == 1
    assert observations[0].coord == "2:23:8"
    assert observations[0].observed_at == datetime(2026, 8, 6, 16, 57, 38, tzinfo=timezone.utc)


def test_missing_server_time_is_unavailable_not_local_now() -> None:
    with pytest.raises(AsteroidReadError, match="серверное время"):
        observations_from_raw({"server_time": None, "asteroids": []})


def test_partial_square_info_fails_closed_instead_of_becoming_empty() -> None:
    with pytest.raises(AsteroidReadError, match="movement-факты"):
        observations_from_raw(
            {
                "server_time": [2026, 8, 6, 20, 57, 38],
                "asteroids": [
                    {"g": 2, "s": 23, "p": 8, "tooltip": "Информация об астероиде"},
                ],
            }
        )


def test_cdp_reader_is_attach_only_and_only_issues_square_info_read_request() -> None:
    source = inspect.getsource(ReadOnlyAsteroidCdpBackend)
    forbidden = (
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "_select_planet(",
        ".click(",
        "SendFleet",
        "ajax_galaxy.php",
    )
    for token in forbidden:
        assert token not in source
    assert "galaxy.php" in source
    assert "#galaxyHolder" in source
    assert "window.currentTime" in source
    assert "fetch('ajax_info.php'" in source
    assert "type:'squareInfo'" in source


def test_reader_requires_current_system_coords_and_never_expands_scope() -> None:
    source = inspect.getsource(ReadOnlyAsteroidCdpBackend)
    assert "coord[0] != current_g" in source
    assert "coord[1] != current_s" in source
    assert "holder.querySelectorAll('a')" in source
