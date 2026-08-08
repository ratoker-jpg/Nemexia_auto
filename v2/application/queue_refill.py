from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from v2.application.read_store import QueueSnapshot
from v2.application.recon_repository import V2TargetRecord
from v2.application.v2_queue import V2QueueRepository
from v2.domain.queue_policy import (
    ExistingQueueFact,
    QueueMode,
    QueueRefillPreview,
    QueueTargetFact,
    build_queue_refill_preview,
)
from v2.domain.recon import LEGACY_METAL_QUEUE_MINIMUM, LEGACY_SPY_REPORT_LOOKBACK_HOURS
from v2.persistence.queue_refill import QueueApplySummary


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _target_fact(item: V2TargetRecord) -> QueueTargetFact:
    return QueueTargetFact(
        coord=item.coord,
        player=item.player,
        enabled=item.enabled,
        blacklisted=item.blacklisted,
        report_id=item.latest_report_id,
        reported_at=_parse_dt(item.last_spy_at),
        metal=item.metal,
        minerals=item.minerals,
        gas=item.gas,
    )


def _existing_fact(item: QueueSnapshot) -> ExistingQueueFact:
    return ExistingQueueFact(
        id=item.id,
        position=item.position,
        state=item.state,
        coord=item.coord,
    )


class QueueRefillService:
    """Application adapter around the pure V2 queue policy and V2-only persistence."""

    def __init__(self, queue: V2QueueRepository) -> None:
        self.queue = queue

    def preview(
        self,
        targets: Sequence[V2TargetRecord],
        *,
        mode: QueueMode,
        now: datetime | None = None,
        queue_size: int = 45,
        minimum_metal: int = LEGACY_METAL_QUEUE_MINIMUM,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
        active_targets: Sequence[str] = (),
    ) -> QueueRefillPreview:
        return build_queue_refill_preview(
            tuple(_target_fact(item) for item in targets),
            tuple(_existing_fact(item) for item in self.queue.list(limit=5000)),
            mode=mode,
            now=now or datetime.now(timezone.utc),
            queue_size=queue_size,
            minimum_metal=minimum_metal,
            lookback_hours=lookback_hours,
            active_targets=active_targets,
        )

    def apply(self, preview: QueueRefillPreview) -> QueueApplySummary:
        return self.queue.apply_refill(preview)
