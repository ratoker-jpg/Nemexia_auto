from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app import RaidManagerApp
from browser import ASTEROID_CANDIDATE_RESERVE, BrowserAutomationError, BrowserWorker, CaptchaRequiredError
from reports import parse_report_paths
from storage import Database
from models import AsteroidObservation, Flight, QueueItem, SpyReport, utc_now
from reports import parse_battle_reports_html, parse_spy_reports_html
from asteroids import advance_coordinate, movement_count, movement_margin_seconds, parse_asteroid_tooltip, predict_coordinate


def main() -> int:
    assert BrowserWorker._is_no_ships_error("Не выбраны корабли")
    assert BrowserWorker._is_no_ships_error("Ошибка: корабли не выбраны")
    assert not BrowserWorker._is_no_ships_error("Недостаточно кораблей для отправки")
    root = Path(__file__).resolve().parent
    seed = root / "targets_seed.json"
    fixtures = root / "tests" / "fixtures"
    battles = parse_battle_reports_html((fixtures / "battle_reports.html").read_text(encoding="utf-8"))
    spies = parse_spy_reports_html((fixtures / "spy_reports.html").read_text(encoding="utf-8"))
    assert len(battles) == 1 and battles[0].coord == "3:39:11" and battles[0].total_loot == 600
    assert len(spies) == 1 and spies[0].energy == 7000 and spies[0].metal == 1000

    # Asteroids move through position 24 into position 1 of the next solar system.
    assert advance_coordinate(3, 38, 24, 1) == (3, 39, 1)
    assert advance_coordinate(3, 39, 24, 1) == (3, 40, 1)
    try:
        advance_coordinate(3, 40, 24, 1)
        raise AssertionError("asteroid must not move outside the 40-system galaxy")
    except ValueError:
        pass
    tooltip = """
      <div>Информация об астероиде</div>
      <div>Последнее перемещение 2026-08-04 20:35:17</div>
      <div>Следующее перемещение 2026-08-04 21:17:17</div>
      <div>Скорость 42 Минут / поле</div>
    """
    observation = parse_asteroid_tooltip(tooltip, 3, 38, 24, datetime(2026, 8, 4, 21, 5, 0))
    assert observation.period_seconds == 42 * 60
    assert movement_count(observation.next_move_server, observation.period_seconds,
                          datetime(2026, 8, 4, 21, 17, 16)) == 0
    predicted, shifts = predict_coordinate(
        observation, datetime(2026, 8, 4, 21, 17, 18), safety_seconds=0
    )
    assert predicted == (3, 39, 1) and shifts == 1
    assert movement_margin_seconds(
        observation.next_move_server, observation.period_seconds, datetime(2026, 8, 4, 21, 17, 18)
    ) == 1

    # Dynamic asteroid selection: one shared worker path uses requested + reserve
    # first, then only the missing count + reserve.  All browser calls are faked.
    assert ASTEROID_CANDIDATE_RESERVE == 5
    assert BrowserWorker.asteroid_candidate_limit(10) == 15
    assert BrowserWorker.asteroid_candidate_limit(1) == 6
    assert BrowserWorker.asteroid_candidate_limit(200) == 200

    def asteroid(index: int, system: int) -> AsteroidObservation:
        return AsteroidObservation(
            g=3, s=system, p=(index % 24) + 1,
            last_move_server=datetime(2026, 8, 4, 20, 35, 17),
            next_move_server=datetime(2026, 8, 4, 21, 17, 17),
            period_seconds=42 * 60,
            scanned_server_at=datetime(2026, 8, 4, 21, 5, 0),
            tooltip_html=tooltip,
        )

    def dynamic_worker(
        batches: list[tuple[list[AsteroidObservation], int, bool]],
        invalid: set[str] | None = None,
    ) -> tuple[BrowserWorker, list[tuple[int, int]], list[str]]:
        worker = BrowserWorker()
        scan_calls: list[tuple[int, int]] = []
        sent_coords: list[str] = []
        async def fake_page(*_args, **_kwargs):
            return object()
        async def no_captcha(*_args, **_kwargs):
            return None
        async def fake_flights():
            return []
        async def fake_recyclers(_home):
            return 500
        async def fake_batch(**kwargs):
            scan_calls.append((int(kwargs["start_system"]), int(kwargs["limit"])))
            return batches.pop(0)
        async def fake_send(item, *_args):
            sent_coords.append(item.coord)
            if item.coord in (invalid or set()):
                raise BrowserAutomationError("invalid candidate")
            return {"target": item.coord, "verified": True}
        worker._select_nemexia_page = fake_page
        worker._assert_no_captcha = no_captcha
        worker.sync_all_flights = fake_flights
        worker.available_recyclers = fake_recyclers
        worker._scan_asteroid_batch = fake_batch
        worker.send_asteroid = fake_send
        worker._is_skippable_asteroid_error = lambda _message: True
        return worker, scan_calls, sent_coords

    first_batch = [asteroid(i, 39) for i in range(15)]
    worker, scan_calls, sent_coords = dynamic_worker([(first_batch, 38, False)])
    payload = asyncio.run(worker.run_asteroid_cycle(
        home=(3, 39, 8), galaxy=3, start_system=39, end_system=1,
        recycler_count=5, max_flights=10, max_slots=15, safety_seconds=10,
    ))
    assert scan_calls == [(39, 15)] and len(sent_coords) == 10
    assert payload["candidates"] == 15 and payload["ready"] == 10 and not payload["error"]

    first_batch = [asteroid(i, 39) for i in range(15)]
    second_batch = [asteroid(100 + i, 38) for i in range(7)]
    invalid = {item.coord for item in first_batch[8:]}
    worker, scan_calls, sent_coords = dynamic_worker([(first_batch, 38, False), (second_batch, 37, False)], invalid)
    payload = asyncio.run(worker.run_asteroid_cycle(
        home=(3, 39, 8), galaxy=3, start_system=39, end_system=1,
        recycler_count=5, max_flights=10, max_slots=15, safety_seconds=10,
    ))
    assert scan_calls == [(39, 15), (38, 7)] and len(sent_coords) == 17
    assert payload["candidates"] == 22 and payload["ready"] == 10 and not payload["error"]

    fifteen = [asteroid(i, 39) for i in range(20)]
    worker, scan_calls, _ = dynamic_worker([(fifteen, 38, False)])
    payload = asyncio.run(worker.run_asteroid_cycle(
        home=(3, 39, 8), galaxy=3, start_system=39, end_system=1,
        recycler_count=5, max_flights=15, max_slots=15, safety_seconds=10,
    ))
    assert scan_calls == [(39, 20)] and payload["ready"] == 15 and not payload["error"]

    duplicate = asteroid(1, 1)
    worker, scan_calls, _ = dynamic_worker([([duplicate, duplicate], 0, True)])
    payload = asyncio.run(worker.run_asteroid_cycle(
        home=(3, 39, 8), galaxy=3, start_system=1, end_system=1,
        recycler_count=5, max_flights=2, max_slots=15, safety_seconds=10,
    ))
    assert scan_calls == [(1, 7)] and payload["candidates"] == 1 and payload["ready"] == 1
    assert payload["error_kind"] == "not_enough_valid"

    captcha_worker = BrowserWorker()
    scan_attempts: list[int] = []
    async def captcha_batch(**_kwargs):
        scan_attempts.append(1)
        raise CaptchaRequiredError("captcha")
    captcha_worker._select_nemexia_page = lambda **_kwargs: asyncio.sleep(0, result=object())
    captcha_worker._assert_no_captcha = lambda *_args, **_kwargs: asyncio.sleep(0)
    captcha_worker.sync_all_flights = lambda: asyncio.sleep(0, result=[])
    captcha_worker.available_recyclers = lambda _home: asyncio.sleep(0, result=500)
    captcha_worker._scan_asteroid_batch = captcha_batch
    try:
        asyncio.run(captcha_worker.run_asteroid_cycle(
            home=(3, 39, 8), galaxy=3, start_system=39, end_system=1,
            recycler_count=5, max_flights=1, max_slots=15, safety_seconds=10,
        ))
        raise AssertionError("captcha must stop the dynamic cycle immediately")
    except CaptchaRequiredError:
        pass
    assert scan_attempts == [1]

    with tempfile.TemporaryDirectory(prefix="nemexia_test_") as temp:
        db = Database(Path(temp) / "test.sqlite3", seed)
        assert db.target_count() == 49, db.target_count()
        targets = db.list_targets()
        assert all(target.coord.count(":") == 2 for target in targets)

        # The transient game error retries exactly once with the same target and ship count.
        retry_worker = BrowserWorker()
        retry_calls: list[tuple[str, int]] = []
        async def fake_page():
            return object()
        async def fake_rows(_page):
            return []
        async def fake_send_once(_page, target, ship_count, _home):
            retry_calls.append((target.coord, ship_count))
            if len(retry_calls) == 1:
                raise BrowserAutomationError("Не выбраны корабли")
            return {"target": target.coord, "ship_count": ship_count}
        async def fake_dismiss(_page):
            return True
        async def fake_diagnostic(_label):
            return None
        retry_worker._ensure_fleets_page = fake_page
        retry_worker._read_flights_from_page = fake_rows
        retry_worker._send_raid_once = fake_send_once
        retry_worker._dismiss_no_ships_popup_and_return = fake_dismiss
        retry_worker._diagnostic = fake_diagnostic
        retried = asyncio.run(retry_worker.send_raid(targets[0], 25, (3, 39, 11)))
        assert retried["target"] == targets[0].coord and retry_calls == [(targets[0].coord, 25)] * 2

        stop_worker = BrowserWorker()
        stop_calls: list[int] = []
        async def always_no_ships(_page, _target, _ship_count, _home):
            stop_calls.append(1)
            raise BrowserAutomationError("Не выбраны корабли")
        stop_worker._ensure_fleets_page = fake_page
        stop_worker._read_flights_from_page = fake_rows
        stop_worker._send_raid_once = always_no_ships
        stop_worker._dismiss_no_ships_popup_and_return = fake_dismiss
        stop_worker._diagnostic = fake_diagnostic
        try:
            asyncio.run(stop_worker.send_raid(targets[0], 25, (3, 39, 11)))
            raise AssertionError("second ship-selection error must stop the retry")
        except BrowserAutomationError:
            pass
        assert stop_calls == [1, 1]

        ranked = sorted(targets, key=lambda target: target.energy, reverse=True)
        db.replace_queue([target.coord for target in ranked[:45]])
        assert len(db.list_queue()) == 45
        db.backup(Path(temp) / "backups")

        # Program-sent flight: exact recorded send time and a single raid count.
        sent = utc_now()
        result = {"fleet_id": "program-1", "target": targets[0].coord, "sent_at": sent.isoformat(),
                  "arrival_at": (sent + timedelta(minutes=5)).isoformat(),
                  "return_at": (sent + timedelta(minutes=10)).isoformat()}
        assert db.add_history(result) is not None
        assert db.add_history(result) is None
        target = db.get_target(targets[0].coord)
        assert target and target.raid_count == 1 and target.last_raid_at == sent

        # Browser/manual flight: derive sent_at from absolute arrival/return and deduplicate re-sync.
        arrival = sent + timedelta(minutes=20)
        returned = sent + timedelta(minutes=40)
        flight = Flight("manual-1", "3:39:11", targets[1].coord, "Атака", arrival, returned)
        assert db.sync_history_from_flights([flight]) == 1
        assert db.sync_history_from_flights([flight]) == 0
        stored = [row for row in db.list_history() if row["fleet_id"] == "manual-1"][0]
        assert stored["sent_at"] == sent.isoformat()
        assert db.get_target(targets[1].coord).raid_count == 1

        # No fleet ID: the normalized coordinate/arrival/return key is stable.
        fallback = Flight(None, "3:39:11", targets[3].coord, "Атака", arrival, returned)
        assert db.sync_history_from_flights([fallback]) == 1
        assert db.sync_history_from_flights([fallback]) == 0
        assert db.get_target(targets[3].coord).raid_count == 1

        # A program result without an ID is joined to the later browser row with an ID.
        delayed_id = {"target": targets[4].coord, "sent_at": sent.isoformat(),
                      "arrival_at": arrival.isoformat(), "return_at": returned.isoformat()}
        assert db.add_history(delayed_id) is not None
        assert db.sync_history_from_flights([Flight("browser-2", "3:39:11", targets[4].coord, "Атака", arrival, returned)]) == 0
        assert db.get_target(targets[4].coord).raid_count == 1

        # Message histories retain snapshots, deduplicate imports and update only a fresh target cache.
        spy = spies[0]
        spy.coord = targets[5].coord
        first, duplicate, refreshed = db.save_spy_reports([spy])
        assert (first, duplicate, refreshed) == (1, 0, 1)
        assert db.save_spy_reports([spy]) == (0, 1, 0)
        newer = SpyReport(coord=spy.coord, player=spy.player, energy=7777,
                          report_at=spy.report_at + timedelta(minutes=1), message_id="spy-2",
                          metal=777, minerals=888, gas=999)
        assert db.save_spy_reports([newer]) == (1, 0, 1)
        latest = db.list_latest_spy_reports()[0]
        assert latest["message_id"] == "spy-2" and db.get_target(spy.coord).metal == 777
        battle = battles[0]
        battle.coord = targets[5].coord
        assert db.save_combat_reports([battle]) == (1, 0, 1)
        assert db.save_combat_reports([battle]) == (0, 1, 0)
        cached = db.get_target(targets[5].coord)
        assert cached and cached.metal == 777 and cached.last_loot_total == 600 and cached.total_loot == 600
        protected = SpyReport(coord="3:2:8", player="Pegasus Team", energy=1, report_at=sent,
                              message_id="protected-spy", metal=999_999)
        db.add_target(protected.coord, protected.player, protected.energy)
        protected_target = db.get_target(protected.coord)
        assert protected_target and protected_target.blacklisted and not protected_target.enabled
        assert db.save_spy_reports([protected]) == (0, 0, 0)
        assert db.upsert_reports([protected]) == (0, 0)
        assert all(row["target_coord"] != protected.coord for row in db.list_latest_spy_reports())
        assert db.clear_spy_reports() == 1
        cleared = db.get_target(targets[5].coord)
        assert cleared and cleared.energy == 0 and cleared.metal is None and cleared.last_spy_at is None
        db.conn.execute(
            "INSERT INTO spy_reports(dedupe_key,target_coord,source,imported_at) VALUES (?,?,?,?)",
            ("legacy-protected", "1:20:19", "test", sent.isoformat()),
        )
        db.conn.commit()
        assert db.clear_spy_reports() == 0
        assert db.conn.execute("SELECT COUNT(*) FROM spy_reports WHERE target_coord='1:20:19'").fetchone()[0] == 1

        # Planning is intentionally based only on the latest spy metal value.
        candidate_coords = [targets[6].coord, targets[7].coord, targets[8].coord]
        candidate_reports = [
            SpyReport(coord=candidate_coords[0], player="low", energy=1, report_at=sent, message_id="metal-low", metal=479_999),
            SpyReport(coord=candidate_coords[1], player="threshold", energy=1, report_at=sent, message_id="metal-threshold", metal=480_000),
            SpyReport(coord=candidate_coords[2], player="high", energy=1, report_at=sent, message_id="metal-high", metal=900_000),
        ]
        db.save_spy_reports(candidate_reports)
        ranking_context = SimpleNamespace(
            targets=db.list_targets(),
            min_metal_queue_var=SimpleNamespace(get=lambda: 480_000),
            _active_coords=lambda: set(),
            _safe_int=lambda var, fallback: int(var.get()),
        )
        ranked_coords = [target.coord for target, _ in RaidManagerApp.ranked_targets(ranking_context)]
        assert ranked_coords[:2] == [candidate_coords[2], candidate_coords[1]]
        assert candidate_coords[0] not in ranked_coords

        # Queue rebuild never duplicates a coordinate while a send is in progress.
        db.clear_queue(include_sending=True)
        db.replace_queue([candidate_coords[2], candidate_coords[1], candidate_coords[2]])
        sending_item = next(item for item in db.list_queue() if item.coord == candidate_coords[2])
        db.set_queue_state(sending_item.id, "sending")
        db.replace_queue([candidate_coords[2], candidate_coords[1], candidate_coords[1]])
        plan = db.list_queue()
        assert [item.coord for item in plan].count(candidate_coords[2]) == 1
        assert [item.coord for item in plan].count(candidate_coords[1]) == 1
        assert [item.position for item in plan] == [1, 2]
        assert next(item for item in plan if item.coord == candidate_coords[2]).state == "sending"
        queued_item = next(item for item in plan if item.coord == candidate_coords[1])
        checked_context = SimpleNamespace(db=db, checked_queue_ids={queued_item.id})
        assert [item.id for item in RaidManagerApp._checked_queue_items(checked_context)] == [queued_item.id]
        missing_item = QueueItem(id=999, coord="9:9:9", position=2, state="queued", created_at=None)
        pairing_context = SimpleNamespace(target_by_coord={
            queued_item.coord: db.get_target(queued_item.coord),
            sending_item.coord: db.get_target(sending_item.coord),
        })
        pairs = RaidManagerApp._queue_target_pairs(pairing_context, [queued_item, missing_item, sending_item])
        assert [(item.coord, target.coord) for item, target in pairs] == [
            (queued_item.coord, queued_item.coord), (sending_item.coord, sending_item.coord)
        ]
        db.set_queue_state(queued_item.id, "sending")
        restored = db.reset_stuck_sending({sending_item.coord})
        assert restored == [queued_item.coord]
        states_after_reset = {item.coord: item.state for item in db.list_queue()}
        assert states_after_reset[queued_item.coord] == "queued"
        assert states_after_reset[sending_item.coord] == "sending"

        # Asteroid scans, cycles and flights persist and deduplicate independently.
        asteroid_obs = AsteroidObservation(
            g=3, s=38, p=24,
            last_move_server=datetime(2026, 8, 4, 20, 35, 17),
            next_move_server=datetime(2026, 8, 4, 21, 17, 17),
            period_seconds=42 * 60,
            scanned_server_at=datetime(2026, 8, 4, 21, 5, 0),
            tooltip_html=tooltip,
        )
        assert db.save_asteroid_scans([asteroid_obs]) == (1, 0)
        assert db.save_asteroid_scans([asteroid_obs]) == (0, 1)
        cycle_id = db.start_asteroid_cycle(15)
        asteroid_sent = utc_now()
        asteroid_result = {
            "fleet_id": "asteroid-1", "source": "3:39:8", "origin_coord": "3:38:24",
            "target": "3:39:1", "ship_count": 5, "shifts": 1,
            "sent_at": asteroid_sent.isoformat(),
            "arrival_at": (asteroid_sent + timedelta(minutes=10)).isoformat(),
            "return_at": (asteroid_sent + timedelta(minutes=20)).isoformat(),
            "one_way_seconds": 600, "round_trip_seconds": 1200, "gas_needed": 12,
        }
        assert db.add_asteroid_flight(asteroid_result, cycle_id=cycle_id) is not None
        assert db.add_asteroid_flight(asteroid_result, cycle_id=cycle_id) is None
        db.finish_asteroid_cycle(
            cycle_id, found=1, sent=1, status="completed",
            next_cycle_at=(asteroid_sent + timedelta(minutes=25)).isoformat(),
        )
        assert db.list_asteroid_cycles(1)[0]["sent"] == 1
        assert db.list_asteroid_flights(1)[0]["target_coord"] == "3:39:1"

        # Missing timing remains explicit unknown, never replaced by the current time.
        unknown = Flight(None, "3:39:11", targets[2].coord, "Атака", None, None)
        assert db.sync_history_from_flights([unknown]) == 1
        unknown_row = [row for row in db.list_history() if row["target"] == targets[2].coord][0]
        assert unknown_row["status"] == "unknown_time" and unknown_row["sent_at"] == ""
        db.close()

        reopened = Database(Path(temp) / "test.sqlite3")
        assert len(reopened.list_history()) == 5, "history must persist after restart"
        reopened.close()

        # Old database without new columns opens and retains existing target data.
        old_path = Path(temp) / "old.sqlite3"
        old = __import__("sqlite3").connect(old_path)
        old.execute("CREATE TABLE targets (coord TEXT PRIMARY KEY, player TEXT, energy INTEGER, g INTEGER, s INTEGER, p INTEGER, enabled INTEGER, blacklisted INTEGER, notes TEXT, last_report_at TEXT, last_raid_at TEXT, raid_count INTEGER, one_way_seconds INTEGER, round_trip_seconds INTEGER, gas_needed INTEGER, created_at TEXT, updated_at TEXT)")
        old.execute("CREATE TABLE history (id INTEGER PRIMARY KEY, fleet_id TEXT, source TEXT, target TEXT NOT NULL, player TEXT, ship_count INTEGER, sent_at TEXT NOT NULL, arrival_at TEXT, return_at TEXT, one_way_seconds INTEGER, round_trip_seconds INTEGER, gas_needed INTEGER, status TEXT, error TEXT, server_info TEXT)")
        old.execute("CREATE TABLE queue (id INTEGER PRIMARY KEY, coord TEXT, position INTEGER, state TEXT, created_at TEXT, updated_at TEXT)")
        old.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        old.execute("INSERT INTO targets VALUES ('1:2:3','Старый',1,1,2,3,1,0,'','',NULL,0,NULL,NULL,NULL,'x','x')")
        old.execute("INSERT INTO queue VALUES (1,'1:2:3',1,'queued','x','x')")
        old.execute("INSERT INTO queue VALUES (2,'1:2:3',2,'sending','x','x')")
        old.commit(); old.close()
        migrated = Database(old_path)
        assert migrated.get_target("1:2:3").player == "Старый"
        assert "last_return_at" in {row["name"] for row in migrated.conn.execute("PRAGMA table_info(targets)")}
        assert "dedupe_key" in {row["name"] for row in migrated.conn.execute("PRAGMA table_info(history)")}
        migrated_queue = migrated.list_queue()
        assert len(migrated_queue) == 1 and migrated_queue[0].coord == "1:2:3" and migrated_queue[0].state == "sending"
        assert migrated.conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_queue_coord_unique'").fetchone()
        migrated.close()
    print("OK: база, стартовые цели, очередь и резервная копия")
    if len(sys.argv) > 1:
        report_path = Path(sys.argv[1])
        reports = parse_report_paths([report_path])
        print(f"OK: извлечено отчётов: {len(reports)}")
        assert reports, "Отчёты не найдены"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
