from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from v2.application.read_store import ReadOnlyStore
from v2.application.report_source import ReconReadSnapshot
from v2.domain.recon import (
    LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ReportReadState,
    SpyReportFact,
    as_utc,
    report_is_fresh,
)
from v2.persistence.database import V2Database


_COORD_RE = re.compile(r"^(\d+)\s*:\s*(\d+)\s*:\s*(\d+)$")


def _normalized_target(value: object) -> str | None:
    match = _COORD_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    parts = tuple(int(part) for part in match.groups())
    if any(part <= 0 for part in parts):
        return None
    return ":".join(str(part) for part in parts)


@dataclass(frozen=True)
class V2ReconRecord:
    id: int
    report_id: str
    target_coord: str
    report_at: str
    energy: int | None
    metal: int | None
    minerals: int | None
    gas: int | None
    source: str
    ingested_at: str


@dataclass(frozen=True)
class V2TargetRecord:
    coord: str
    player: str
    enabled: bool
    blacklisted: bool
    notes: str
    latest_report_id: str | None
    last_spy_at: str | None
    energy: int | None
    metal: int | None
    minerals: int | None
    gas: int | None


@dataclass(frozen=True)
class ReconIngestResult:
    inserted: int
    duplicates: int
    rejected_partial: int
    rejected_stale: int

    @property
    def accepted(self) -> int:
        return self.inserted + self.duplicates


class V2ReconRepository:
    """Own normalized reconnaissance snapshots and target metadata in V2 SQLite."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def import_legacy_targets(self, legacy: ReadOnlyStore) -> int:
        """Seed missing target metadata only; never overwrite V2-owned rows."""
        payload = [
            {
                "coord": item.coord,
                "player": item.player,
                "enabled": item.enabled,
                "blacklisted": item.blacklisted,
                "notes": item.notes,
            }
            for item in legacy.list_targets(limit=5000)
        ]
        return self.database.import_recon_target_rows(payload)

    def ingest_snapshot(
        self,
        snapshot: ReconReadSnapshot,
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconIngestResult:
        if snapshot.state is not ReportReadState.FRESH:
            return ReconIngestResult(0, 0, 0, len(snapshot.reports))
        return self.ingest_reports(snapshot.fresh_reports, now=now, lookback_hours=lookback_hours)

    def ingest_reports(
        self,
        reports: Sequence[SpyReportFact],
        *,
        now: datetime | None = None,
        lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    ) -> ReconIngestResult:
        current = as_utc(now or datetime.now(timezone.utc))
        payload: list[dict[str, object]] = []
        rejected_partial = 0
        rejected_stale = 0
        for report in reports:
            report_id = str(report.report_id or "").strip()
            target = _normalized_target(report.target)
            if not report.has_verifiable_identity or not report_id or target is None:
                rejected_partial += 1
                continue
            if not report_is_fresh(report, now=current, lookback_hours=lookback_hours):
                rejected_stale += 1
                continue
            payload.append(
                {
                    "report_id": report_id,
                    "target": target,
                    "report_at": as_utc(report.reported_at).replace(microsecond=0).isoformat(),
                    "energy": report.energy,
                    "metal": report.metal,
                    "minerals": report.minerals,
                    "gas": report.gas,
                    "source": str(report.source or "messages").strip() or "messages",
                }
            )
        inserted = self.database.insert_recon_report_rows(payload)
        return ReconIngestResult(
            inserted=inserted,
            duplicates=max(0, len(payload) - inserted),
            rejected_partial=rejected_partial,
            rejected_stale=rejected_stale,
        )

    def list_recon(self, *, limit: int = 2000) -> list[V2ReconRecord]:
        return [
            V2ReconRecord(
                id=int(row["id"]),
                report_id=str(row["report_id"]),
                target_coord=str(row["target"]),
                report_at=str(row["report_at"]),
                energy=row.get("energy"),
                metal=row.get("metal"),
                minerals=row.get("minerals"),
                gas=row.get("gas"),
                source=str(row.get("source") or "messages"),
                ingested_at=str(row["ingested_at"]),
            )
            for row in self.database.list_recon_report_rows(limit=limit)
        ]

    def list_targets(self, *, limit: int = 5000) -> list[V2TargetRecord]:
        return [
            V2TargetRecord(
                coord=str(row["coord"]),
                player=str(row.get("player") or "—"),
                enabled=bool(row.get("enabled")),
                blacklisted=bool(row.get("blacklisted")),
                notes=str(row.get("notes") or ""),
                latest_report_id=(str(row["report_id"]) if row.get("report_id") is not None else None),
                last_spy_at=(str(row["report_at"]) if row.get("report_at") is not None else None),
                energy=row.get("energy"),
                metal=row.get("metal"),
                minerals=row.get("minerals"),
                gas=row.get("gas"),
            )
            for row in self.database.list_recon_target_rows(limit=limit)
        ]
