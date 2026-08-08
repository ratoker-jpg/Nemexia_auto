from __future__ import annotations

import inspect

from v2.infrastructure.cdp_asteroid_backend import (
    V2AsteroidCdpBackend,
    select_verified_asteroid_flight,
)


def test_new_flight_verification_requires_new_id_exact_target_and_gas_mission() -> None:
    rows = (
        {"id": "10", "target": "2:23:8", "mission": "Добыча газа", "source": "2:22:3"},
        {"id": "11", "target": "2:23:9", "mission": "Добыча газа", "source": "2:22:3"},
        {"id": "12", "target": "2:23:8", "mission": "Атака", "source": "2:22:3"},
        {"id": "13", "target": "2:23:8", "mission": " Добыча газа ", "source": "2:22:3"},
    )
    matched = select_verified_asteroid_flight(
        rows,
        before_ids=frozenset({"10"}),
        target="2:23:8",
    )
    assert matched is not None and matched["id"] == "13"


def test_existing_or_wrong_target_or_wrong_mission_never_verifies() -> None:
    rows = (
        {"id": "10", "target": "2:23:8", "mission": "Добыча газа", "source": "2:22:3"},
        {"id": "11", "target": "2:23:9", "mission": "Добыча газа", "source": "2:22:3"},
        {"id": "12", "target": "2:23:8", "mission": "Атака", "source": "2:22:3"},
    )
    assert select_verified_asteroid_flight(
        rows, before_ids=frozenset({"10"}), target="2:23:8"
    ) is None


def test_backend_is_attach_only_and_has_exactly_one_sendfleet_click_site() -> None:
    source = inspect.getsource(V2AsteroidCdpBackend)
    for forbidden in (
        ".goto(",
        "new_page(",
        "refreshGalaxy(",
        "ajax_galaxy.php",
        "_select_planet(",
        "launch_",
    ):
        assert forbidden not in source
    assert source.count("await button.click()") == 1
    assert "Exactly one remote mutation attempt" in source
    assert "page.expect_response" in source
    assert '"ajax_fleets.php" in response.url' in source
    assert '"type=SendFleet" in (response.request.post_data or "")' in source


def test_prepare_and_send_recheck_live_asteroid_without_navigation() -> None:
    source = inspect.getsource(V2AsteroidCdpBackend)
    assert source.count("await self._recheck_observation(command.observation") >= 2
    assert "fetch('ajax_info.php'" in source
    assert "type:'squareInfo'" in source
    assert "_matching_galaxy_page" in source
    assert "Переключи её вручную" in source


def test_preparation_pins_recycler_mission_capacity_and_iterative_timing() -> None:
    source = inspect.getsource(V2AsteroidCdpBackend)
    for token in (
        "#ship_1_11_max",
        "#FleetsCount",
        "#MaxFleets",
        "select#mission",
        "selectMissionImg",
        "shipsCheck",
        "#target_c1",
        "#target_c2",
        "#target_c3",
        "FlyCheck",
        "window.seconds",
        "window.seconds2",
        "#missionGasNeeded",
        "ASTEROID_PLAN_MAX_ITERATIONS",
        "movement_margin_seconds",
    ):
        assert token in source


def test_post_attempt_failures_are_ambiguous_not_retried() -> None:
    source = inspect.getsource(V2AsteroidCdpBackend)
    assert "AsteroidDispatchAmbiguous" in source
    assert "автоматический повтор запрещён" in source
    assert "exact new-flight verification отсутствует" in source
    assert "for attempt" not in source
    assert "retry" not in source.casefold()
