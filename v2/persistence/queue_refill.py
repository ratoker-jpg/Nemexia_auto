from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from v2.domain.queue_policy import (
    PROTECTED_QUEUE_STATES,
    REPLACEABLE_QUEUE_STATES,
    QueueDesiredRow,
)
from v2.persistence.database import V2Database, V2DatabaseError


@dataclass(frozen=True)
class QueueApplySummary:
    created: int
    updated: int
    removed: int


class V2QueueRefillStore:
    """Transactional V2-only queue refill persistence adapter."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def apply(self, desired: Sequence[QueueDesiredRow]) -> QueueApplySummary:
        rows = tuple(desired)
        desired_coords = [item.coord for item in rows]
        if len(desired_coords) != len(set(desired_coords)):
            raise V2DatabaseError("Queue refill contains duplicate desired coordinates")

        conn = self.database._require_conn()
        created = updated = removed = 0
        with conn:
            existing = [dict(row) for row in conn.execute("SELECT * FROM raid_queue ORDER BY id").fetchall()]
            protected_by_coord: dict[str, list[dict[str, object]]] = {}
            replaceable_by_coord: dict[str, list[dict[str, object]]] = {}
            for row in existing:
                state = str(row["state"])
                coord = str(row["coord"])
                if state in PROTECTED_QUEUE_STATES:
                    protected_by_coord.setdefault(coord, []).append(row)
                elif state in REPLACEABLE_QUEUE_STATES:
                    replaceable_by_coord.setdefault(coord, []).append(row)

            duplicate_protected = sorted(coord for coord, items in protected_by_coord.items() if len(items) > 1)
            if duplicate_protected:
                raise V2DatabaseError(
                    "Existing protected queue has duplicate targets: " + ", ".join(duplicate_protected)
                )
            conflict = sorted(set(desired_coords) & set(protected_by_coord))
            if conflict:
                raise V2DatabaseError(
                    "Queue refill would duplicate protected targets: " + ", ".join(conflict)
                )

            desired_set = set(desired_coords)
            removable_ids: list[int] = []
            for coord, items in replaceable_by_coord.items():
                if coord not in desired_set:
                    removable_ids.extend(int(item["id"]) for item in items)
                    continue
                # Reuse one deterministic row; remove any replaceable duplicates.
                items.sort(key=lambda item: int(item["id"]))
                removable_ids.extend(int(item["id"]) for item in items[1:])
                replaceable_by_coord[coord] = items[:1]

            if removable_ids:
                placeholders = ",".join("?" for _ in removable_ids)
                conn.execute(f"DELETE FROM raid_queue WHERE id IN ({placeholders})", tuple(removable_ids))
                removed += len(removable_ids)

            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            for item in rows:
                reusable = replaceable_by_coord.get(item.coord, [])
                values = (
                    int(item.position),
                    "queued",
                    str(item.coord),
                    str(item.player or "—"),
                    item.metal,
                    item.minerals,
                    item.gas,
                    str(item.last_spy_at),
                    int(bool(item.enabled)),
                    int(bool(item.blacklisted)),
                    now,
                )
                if reusable:
                    conn.execute(
                        """UPDATE raid_queue
                           SET position=?, state=?, coord=?, player=?, metal=?, minerals=?, gas=?,
                               last_spy_at=?, enabled=?, blacklisted=?, updated_at=?
                         WHERE id=?""",
                        values + (int(reusable[0]["id"]),),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO raid_queue(
                            imported_legacy_id, position, state, coord, player, metal, minerals, gas,
                            last_spy_at, enabled, blacklisted, created_at, updated_at
                        ) VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            int(item.position),
                            "queued",
                            str(item.coord),
                            str(item.player or "—"),
                            item.metal,
                            item.minerals,
                            item.gas,
                            str(item.last_spy_at),
                            int(bool(item.enabled)),
                            int(bool(item.blacklisted)),
                            now,
                            now,
                        ),
                    )
                    created += 1

            active_rows = conn.execute(
                """SELECT coord, COUNT(*) AS n FROM raid_queue
                   WHERE state IN ('queued','sending','sent','ambiguous')
                   GROUP BY coord HAVING COUNT(*) > 1"""
            ).fetchall()
            if active_rows:
                raise V2DatabaseError(
                    "Queue refill produced duplicate active targets: "
                    + ", ".join(str(row[0]) for row in active_rows)
                )

        return QueueApplySummary(created=created, updated=updated, removed=removed)
