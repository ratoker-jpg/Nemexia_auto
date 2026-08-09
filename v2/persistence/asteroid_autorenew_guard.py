from __future__ import annotations

from dataclasses import dataclass

from v2.persistence.database import V2Database


@dataclass(frozen=True)
class UnresolvedAsteroidAction:
    request_id: str
    status: str
    source: str
    target: str


class AsteroidAutorenewGuardRepository:
    """Repository-wide scheduler gates that must not use a bounded recent list."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def unresolved_action(self) -> UnresolvedAsteroidAction | None:
        row = self.database._require_conn().execute(
            """SELECT request_id,status,source,target
                 FROM asteroid_actions
                WHERE status IN ('pending','ambiguous')
                ORDER BY id ASC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        return UnresolvedAsteroidAction(
            request_id=str(row["request_id"]),
            status=str(row["status"]),
            source=str(row["source"]),
            target=str(row["target"]),
        )
