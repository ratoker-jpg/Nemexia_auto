from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from v2.application.queue_refill import QueueRefillService
from v2.application.recon_repository import V2TargetRecord
from v2.application.v2_queue import V2QueueRepository
from v2.domain.queue_policy import (
    ExistingQueueFact,
    QueueSkipReason,
    QueueTargetFact,
    build_queue_refill_preview,
)
from v2.persistence.database import V2Database, V2DatabaseError


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def target(
    coord: str,
    *,
    metal: int | None = 600_000,
    minerals: int | None = 600_000,
    enabled: bool = True,
    blacklisted: bool = False,
    report_id: str | None = None,
    at: datetime | None = None,
) -> QueueTargetFact:
    return QueueTargetFact(
        coord=coord,
        player=f"P-{coord}",
        enabled=enabled,
        blacklisted=blacklisted,
        report_id=report_id or f"r-{coord}",
        reported_at=at or NOW - timedelta(minutes=5),
        metal=metal,
        minerals=minerals,
        gas=10_000,
    )


def existing(row_id: int, coord: str, state: str, position: int = 1) -> ExistingQueueFact:
    return ExistingQueueFact(id=row_id, position=position, state=state, coord=coord)


def test_metal_policy_is_ranked_and_respects_all_target_gates() -> None:
    targets = (
        target("3:1:1", metal=900_000),
        target("3:1:2", metal=850_000),
        target("3:1:3", metal=700_000),
        target("3:1:4", metal=650_000),
        target("3:1:5", metal=470_000),
        target("3:1:6", metal=990_000, enabled=False),
        target("3:1:7", metal=980_000, blacklisted=True),
        target("3:1:8", metal=970_000, at=NOW - timedelta(hours=25)),
        target("3:1:9", metal=960_000),
    )
    current = (
        existing(1, "3:1:1", "sent"),
        existing(2, "3:1:3", "queued"),
        existing(3, "3:9:9", "queued"),
    )
    preview = build_queue_refill_preview(
        targets,
        current,
        mode="metal",
        now=NOW,
        queue_size=2,
        active_targets=("3:1:9",),
    )
    assert [row.coord for row in preview.desired] == ["3:1:2", "3:1:3"]
    assert preview.added == ("3:1:2",)
    assert preview.kept == ("3:1:3",)
    assert preview.removed == ("3:9:9",)
    assert preview.protected == ("3:1:1",)
    reasons = {(item.coord, item.reason) for item in preview.skipped}
    assert ("3:1:1", QueueSkipReason.PROTECTED_EXISTING) in reasons
    assert ("3:1:4", QueueSkipReason.OUTSIDE_LIMIT) in reasons
    assert ("3:1:5", QueueSkipReason.METAL_BELOW_MINIMUM) in reasons
    assert ("3:1:6", QueueSkipReason.DISABLED) in reasons
    assert ("3:1:7", QueueSkipReason.BLACKLISTED) in reasons
    assert ("3:1:8", QueueSkipReason.STALE_REPORT) in reasons
    assert ("3:1:9", QueueSkipReason.ACTIVE_TARGET) in reasons


def test_manual_minerals_and_autofarm_are_distinct_contracts() -> None:
    targets = (
        target("2:1:1", metal=100, minerals=1),
        target("2:1:2", metal=900_000, minerals=499_999),
        target("2:1:3", metal=100_000, minerals=500_000),
        target("2:1:4", metal=800_000, minerals=500_000),
        target("2:1:5", minerals=None),
    )
    manual = build_queue_refill_preview(targets, (), mode="minerals", now=NOW, queue_size=10)
    assert [row.coord for row in manual.desired] == ["2:1:3", "2:1:4", "2:1:2", "2:1:1"]
    assert any(item.coord == "2:1:5" and item.reason is QueueSkipReason.MINERALS_MISSING for item in manual.skipped)

    auto = build_queue_refill_preview(targets, (), mode="autofarm", now=NOW, queue_size=10)
    # Equal minerals are ranked by metal descending for the accepted legacy AutoFarm policy.
    assert [row.coord for row in auto.desired] == ["2:1:4", "2:1:3"]
    reasons = {item.coord: item.reason for item in auto.skipped}
    assert reasons["2:1:1"] is QueueSkipReason.AUTOFARM_BELOW_MINIMUM
    assert reasons["2:1:2"] is QueueSkipReason.AUTOFARM_BELOW_MINIMUM


def test_same_input_is_deterministic_and_duplicate_target_input_is_collapsed() -> None:
    rows = (
        target("1:2:3", metal=700_000),
        target("1:2:1", metal=700_000),
        target("1:2:2", metal=800_000),
        target("1:2:2", metal=800_000, report_id="duplicate"),
    )
    first = build_queue_refill_preview(rows, (), mode="metal", now=NOW, queue_size=3)
    second = build_queue_refill_preview(tuple(reversed(rows)), (), mode="metal", now=NOW, queue_size=3)
    assert first.desired == second.desired
    assert [row.coord for row in first.desired] == ["1:2:2", "1:2:1", "1:2:3"]
    assert sum(item.reason is QueueSkipReason.DUPLICATE_INPUT for item in first.skipped) == 1


def _target_record(coord: str, *, metal: int, minerals: int) -> V2TargetRecord:
    return V2TargetRecord(
        coord=coord,
        player=f"P-{coord}",
        enabled=True,
        blacklisted=False,
        notes="",
        latest_report_id=f"report-{coord}",
        last_spy_at=(NOW - timedelta(minutes=2)).isoformat(),
        energy=7000,
        metal=metal,
        minerals=minerals,
        gas=20_000,
    )


def test_apply_refill_preserves_protected_rows_and_removes_replaceable_duplicates(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        db.import_raid_queue_rows((
            {"legacy_id":1,"position":1,"state":"sent","coord":"3:1:1","player":"protected","metal":1,"minerals":1,"gas":1,"last_spy_at":NOW.isoformat(),"enabled":True,"blacklisted":False},
            {"legacy_id":2,"position":2,"state":"queued","coord":"3:1:2","player":"old","metal":1,"minerals":1,"gas":1,"last_spy_at":NOW.isoformat(),"enabled":True,"blacklisted":False},
            {"legacy_id":3,"position":3,"state":"failed","coord":"3:1:3","player":"failed","metal":1,"minerals":1,"gas":1,"last_spy_at":NOW.isoformat(),"enabled":True,"blacklisted":False},
            {"legacy_id":4,"position":4,"state":"queued","coord":"3:9:9","player":"remove","metal":1,"minerals":1,"gas":1,"last_spy_at":NOW.isoformat(),"enabled":True,"blacklisted":False},
        ))
        queue = V2QueueRepository(db)
        service = QueueRefillService(queue)
        preview = service.preview(
            (
                _target_record("3:1:1", metal=999_000, minerals=999_000),
                _target_record("3:1:2", metal=800_000, minerals=800_000),
                _target_record("3:1:3", metal=700_000, minerals=700_000),
            ),
            mode="metal",
            now=NOW,
            queue_size=5,
        )
        assert preview.protected == ("3:1:1",)
        assert preview.kept == ("3:1:2",)
        assert preview.added == ("3:1:3",)
        assert preview.removed == ("3:9:9",)

        applied = service.apply(preview)
        assert applied.created == 0
        assert applied.updated == 2
        assert applied.removed == 1
        final = queue.list()
        assert [(row.coord, row.state) for row in final] == [
            ("3:1:2", "queued"),
            ("3:1:3", "queued"),
            ("3:1:1", "sent"),
        ]
        protected = next(row for row in final if row.coord == "3:1:1")
        assert protected.id == 1 and protected.player == "protected"
        assert len({row.coord for row in final}) == len(final)

        # Reapplying the same desired state does not create duplicates or new rows.
        again = service.apply(service.preview(
            (
                _target_record("3:1:1", metal=999_000, minerals=999_000),
                _target_record("3:1:2", metal=800_000, minerals=800_000),
                _target_record("3:1:3", metal=700_000, minerals=700_000),
            ),
            mode="metal", now=NOW, queue_size=5,
        ))
        assert again.created == 0 and again.removed == 0
        assert len({row.coord for row in queue.list()}) == len(queue.list())


def test_persistence_fails_closed_if_desired_conflicts_with_protected_row(tmp_path: Path) -> None:
    with V2Database(tmp_path / "v2.sqlite3") as db:
        db.import_raid_queue_rows(({
            "legacy_id":1,"position":1,"state":"ambiguous","coord":"3:1:1","player":"P",
            "metal":1,"minerals":1,"gas":1,"last_spy_at":NOW.isoformat(),"enabled":True,"blacklisted":False,
        },))
        service = QueueRefillService(V2QueueRepository(db))
        preview = build_queue_refill_preview((target("3:1:2"),), (), mode="metal", now=NOW)
        forged = preview.__class__(
            mode=preview.mode,
            queue_size=preview.queue_size,
            desired=(preview.desired[0].__class__(1,"3:1:1","P",600000,600000,1,NOW.isoformat()),),
            added=("3:1:1",), kept=(), removed=(), protected=(), skipped=(),
        )
        with pytest.raises(V2DatabaseError, match="protected targets"):
            service.apply(forged)
