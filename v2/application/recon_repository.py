from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from v2.application.read_store import ReconSnapshot, TargetSnapshot
from v2.domain.recon import SpyReportFact, report_is_fresh
from v2.persistence.database import V2Database


@dataclass(frozen=True)
class ReconIngestionResult:
    added_report_ids: tuple[str, ...]
    duplicate_report_ids: tuple[str, ...]
    rejected_report_ids: tuple[str, ...]

    @property
    def added(self) -> int:
        return len(self.added_report_ids)


class V2ReconRepository:
    """V2-owned normalized spy reports plus latest target snapshots."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def import_legacy_targets_if_empty(self, targets: Iterable[TargetSnapshot]) -> int:
        conn = self.database._require_conn()
        if int(conn.execute("SELECT COUNT(*) FROM recon_targets").fetchone()[0]) > 0:
            return 0
        rows = list(targets)
        if not rows:
            return 0
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = [
            (
                item.coord, item.player, int(item.enabled), int(item.blacklisted), item.notes,
                item.energy, item.metal, item.minerals, item.gas, item.last_spy_at,
                item.raid_count, item.last_raid_at, item.last_return_at, now,
            )
            for item in rows
        ]
        with conn:
            conn.executemany(
                """INSERT INTO recon_targets(
                    coord, player, enabled, blacklisted, notes, energy, metal, minerals, gas,
                    last_spy_at, raid_count, last_raid_at, last_return_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                payload,
            )
        return len(payload)

    def ingest_fresh(
        self,
        reports: Iterable[SpyReportFact],
        *,
        now: datetime | None = None,
        lookback_hours: int = 24,
    ) -> ReconIngestionResult:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        added: list[str] = []
        duplicates: list[str] = []
        rejected: list[str] = []
        conn = self.database._require_conn()

        for report in sorted(
            tuple(reports),
            key=lambda item: ((item.reported_at or datetime.min.replace(tzinfo=timezone.utc)), item.report_id or ""),
        ):
            report_id = str(report.report_id or "").strip()
            if (
                not report_id
                or not report.target
                or report.reported_at is None
                or report.metal is None
                or report.minerals is None
                or not report_is_fresh(report, now=current, lookback_hours=lookback_hours)
            ):
                rejected.append(report_id or "<missing>")
                continue
            report_at = report.reported_at.astimezone(timezone.utc).isoformat()
            ingested_at = current.replace(microsecond=0).isoformat()
            try:
                with conn:
                    conn.execute(
                        """INSERT INTO recon_reports(
                            report_id, target_coord, report_at, energy, metal, minerals, gas, source, ingested_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            report_id, report.target, report_at, report.energy, report.metal,
                            report.minerals, report.gas, report.source, ingested_at,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO recon_targets(
                            coord, player, enabled, blacklisted, notes, energy, metal, minerals, gas,
                            last_spy_at, latest_report_id, raid_count, updated_at
                        ) VALUES(?, '—', 1, 0, '', ?, ?, ?, ?, ?, ?, 0, ?)
                        ON CONFLICT(coord) DO UPDATE SET
                            energy=CASE WHEN excluded.last_spy_at >= COALESCE(recon_targets.last_spy_at, '') THEN excluded.energy ELSE recon_targets.energy END,
                            metal=CASE WHEN excluded.last_spy_at >= COALESCE(recon_targets.last_spy_at, '') THEN excluded.metal ELSE recon_targets.metal END,
                            minerals=CASE WHEN excluded.last_spy_at >= COALESCE(recon_targets.last_spy_at, '') THEN excluded.minerals ELSE recon_targets.minerals END,
                            gas=CASE WHEN excluded.last_spy_at >= COALESCE(recon_targets.last_spy_at, '') THEN excluded.gas ELSE recon_targets.gas END,
                            latest_report_id=CASE WHEN excluded.last_spy_at >= COALESCE(recon_targets.last_spy_at, '') THEN excluded.latest_report_id ELSE recon_targets.latest_report_id END,
                            last_spy_at=MAX(COALESCE(recon_targets.last_spy_at, ''), excluded.last_spy_at),
                            updated_at=excluded.updated_at""",
                        (
                            report.target, report.energy, report.metal, report.minerals, report.gas,
                            report_at, report_id, ingested_at,
                        ),
                    )
            except Exception as exc:
                if "UNIQUE constraint failed: recon_reports.report_id" in str(exc):
                    duplicates.append(report_id)
                    continue
                raise
            added.append(report_id)
        return ReconIngestionResult(tuple(added), tuple(duplicates), tuple(rejected))

    def list_recon(self, *, limit: int = 2000) -> list[ReconSnapshot]:
        rows = self.database._require_conn().execute(
            """SELECT id, target_coord, report_at, energy, metal, minerals, gas, source
               FROM recon_reports ORDER BY report_at DESC, id DESC LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [
            ReconSnapshot(
                id=int(row["id"]), target_coord=str(row["target_coord"]), report_at=str(row["report_at"]),
                energy=row["energy"], metal=row["metal"], minerals=row["minerals"], gas=row["gas"],
                population=None, ships=None, defense=None, completeness="resources",
                source=str(row["source"] or "messages"),
            )
            for row in rows
        ]

    def list_targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        rows = self.database._require_conn().execute(
            """SELECT coord, player, energy, enabled, blacklisted, notes, metal, minerals, gas,
                      last_spy_at, raid_count, last_raid_at, last_return_at
               FROM recon_targets
               ORDER BY CAST(substr(coord,1,instr(coord,':')-1) AS INTEGER), coord
               LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [
            TargetSnapshot(
                coord=str(row["coord"]), player=str(row["player"] or "—"), energy=int(row["energy"] or 0),
                enabled=bool(row["enabled"]), blacklisted=bool(row["blacklisted"]), notes=str(row["notes"] or ""),
                metal=row["metal"], minerals=row["minerals"], gas=row["gas"], last_spy_at=row["last_spy_at"],
                raid_count=int(row["raid_count"] or 0), last_raid_at=row["last_raid_at"], last_return_at=row["last_return_at"],
            )
            for row in rows
        ]
