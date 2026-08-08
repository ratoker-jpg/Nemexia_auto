from __future__ import annotations

from v2.application.read_store import QueueSnapshot, ReadOnlyStore
from v2.domain.queue_policy import QueueRefillPreview
from v2.persistence.database import V2Database
from v2.persistence.queue_refill import QueueApplySummary, V2QueueRefillStore


class V2QueueRepository:
    """Own mutable raid-queue state in V2 SQLite only."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def import_legacy_if_empty(self, legacy: ReadOnlyStore) -> int:
        rows = legacy.list_plan(limit=5000)
        payload = [
            {
                "legacy_id": item.id,
                "position": item.position,
                "state": item.state,
                "coord": item.coord,
                "player": item.player,
                "metal": item.metal,
                "minerals": item.minerals,
                "gas": item.gas,
                "last_spy_at": item.last_spy_at,
                "enabled": item.enabled,
                "blacklisted": item.blacklisted,
            }
            for item in rows
        ]
        return self.database.import_raid_queue_rows(payload)

    def list(self, *, limit: int = 5000) -> list[QueueSnapshot]:
        return [
            QueueSnapshot(
                id=int(row["id"]),
                position=int(row["position"]),
                state=str(row["state"]),
                coord=str(row["coord"]),
                player=str(row["player"] or "—"),
                metal=row.get("metal"),
                minerals=row.get("minerals"),
                gas=row.get("gas"),
                last_spy_at=row.get("last_spy_at"),
                enabled=bool(row.get("enabled")),
                blacklisted=bool(row.get("blacklisted")),
            )
            for row in self.database.list_raid_queue_rows(limit=limit)
        ]

    def set_state(self, queue_id: int, state: str) -> None:
        self.database.update_raid_queue_state(queue_id, state)

    def apply_refill(self, preview: QueueRefillPreview) -> QueueApplySummary:
        """Apply only the exact pure-policy desired rows; protected states stay untouched."""
        return V2QueueRefillStore(self.database).apply(preview.desired)
