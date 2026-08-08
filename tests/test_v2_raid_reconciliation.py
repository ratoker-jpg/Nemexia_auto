from pathlib import Path

from v2.application.flight_source import ActiveFlightSnapshot
from v2.application.live_flight_semantics import build_live_flight_policy, classify_active_flights
from v2.application.raid_actions import RaidActionService, RaidCommand, RaidDispatchResult, RaidPreparation
from v2.application.raid_journal import RaidDispatchCoordinator
from v2.application.raid_reconciliation import reconcile_unresolved_raids
from v2.persistence.database import V2Database


class NoSendBackend:
    def prepare(self, command: RaidCommand) -> RaidPreparation:
        raise AssertionError("reconciliation must not prepare")

    def dispatch(self, command: RaidCommand) -> RaidDispatchResult:
        raise AssertionError("reconciliation must not dispatch")

    def close(self) -> None:
        pass


def classified(*flights: ActiveFlightSnapshot):
    policy = build_live_flight_policy(
        {"home_g": 3, "home_s": 39, "home_p": 11},
        owned_planets=("3:39:11",),
    )
    return classify_active_flights(flights, policy)


def make_ambiguous(db: V2Database, request_id: str = "r1") -> RaidDispatchCoordinator:
    db.begin_raid_action(
        request_id=request_id,
        source="3:39:11",
        target="3:1:2",
        player="Alpha",
        ship_count=25,
    )
    db.finish_raid_action(
        request_id,
        status="ambiguous",
        sent_at="2026-08-08T10:00:00+00:00",
        detail="verification timeout",
    )
    return RaidDispatchCoordinator(RaidActionService(NoSendBackend(), enabled=True), db)


def test_exact_new_live_attack_resolves_ambiguous_record(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = make_ambiguous(db)
        flights = classified(
            ActiveFlightSnapshot(
                source="3:39:11",
                target="3:1:2",
                mission="Атака",
                departure_at="2026-08-08T10:00:05+00:00",
                arrival_at="2026-08-08T10:05:00+00:00",
                return_at="2026-08-08T10:10:00+00:00",
                fleet_id="77",
            )
        )
        result = reconcile_unresolved_raids(coordinator, coordinator.recent(), flights)
        assert [(item.request_id, item.fleet_id) for item in result] == [("r1", "77")]
        record = coordinator.record("r1")
        assert record is not None
        assert record.status == "verified"
        assert record.fleet_id == "77"


def test_reconciliation_never_guesses_between_two_matching_attacks(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = make_ambiguous(db)
        flights = classified(
            ActiveFlightSnapshot(
                source="3:39:11", target="3:1:2", mission="Атака",
                departure_at="2026-08-08T10:00:05+00:00", fleet_id="77",
            ),
            ActiveFlightSnapshot(
                source="3:39:11", target="3:1:2", mission="Атака",
                departure_at="2026-08-08T10:00:06+00:00", fleet_id="78",
            ),
        )
        assert reconcile_unresolved_raids(coordinator, coordinator.recent(), flights) == []
        assert coordinator.record("r1").status == "ambiguous"


def test_older_or_non_attack_flight_cannot_resolve_request(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        coordinator = make_ambiguous(db)
        flights = classified(
            ActiveFlightSnapshot(
                source="3:39:11", target="3:1:2", mission="Атака",
                departure_at="2026-08-08T09:59:59+00:00", fleet_id="70",
            ),
            ActiveFlightSnapshot(
                source="3:39:11", target="3:1:2", mission="Транспорт",
                departure_at="2026-08-08T10:00:05+00:00", fleet_id="71",
            ),
        )
        assert reconcile_unresolved_raids(coordinator, coordinator.recent(), flights) == []
        assert coordinator.record("r1").status == "ambiguous"
