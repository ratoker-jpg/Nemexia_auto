from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from v2.application.read_store import ReconSnapshot, TargetSnapshot
from v2.domain.recon import SpyReportFact, report_is_fresh
from v2.persistence.database import V2Database, V2DatabaseError


RECON_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReconIngestionResult:
    added_report_ids: tuple[str, ...]
    duplicate_report_ids: tuple[str, ...]
    rejected_report_ids: tuple[str, ...]

    @property
    def added(self) -> int:
        return len(self.added_report_ids)


class V2ReconRepository:
    """V2-owned normalized report provenance plus latest target snapshots."""

    def __init__(self, database: V2Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = self.database._require_conn()
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recon_schema_meta'"
        ).fetchone()
        if existing is not None:
            row = conn.execute("SELECT MAX(version) FROM recon_schema_meta").fetchone()
            current = int(row[0] or 0)
            if current > RECON_SCHEMA_VERSION:
                raise V2DatabaseError(
                    f"Recon component schema {current} is newer than supported {RECON_SCHEMA_VERSION}"
                )
            return

        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """CREATE TABLE recon_schema_meta (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE recon_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL UNIQUE,
                    target_coord TEXT NOT NULL,
                    report_at TEXT NOT NULL,
                    energy INTEGER,
                    metal INTEGER NOT NULL,
                    minerals INTEGER NOT NULL,
                    gas INTEGER,
                    source TEXT NOT NULL,
                    ingested_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE INDEX idx_recon_reports_target_time
                   ON recon_reports(target_coord, report_at DESC, id DESC)"""
            )
            conn.execute(
                """CREATE TABLE recon_targets (
                    coord TEXT PRIMARY KEY,
                    player TEXT NOT NULL DEFAULT '—',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    blacklisted INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    energy INTEGER NOT NULL DEFAULT 0,
                    metal INTEGER,
                    minerals INTEGER,
                    gas INTEGER,
                    last_spy_at TEXT,
                    latest_report_id TEXT,
                    raid_count INTEGER NOT NULL DEFAULT 0,
                    last_raid_at TEXT,
                    last_return_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(latest_report_id) REFERENCES recon_reports(report_id)
                )"""
            )
            conn.execute(
                """CREATE INDEX idx_recon_targets_policy
                   ON recon_targets(enabled, blacklisted, last_spy_at DESC, coord)"""
            )
            conn.execute(
                "INSERT INTO recon_schema_meta(version, applied_at) VALUES(?, ?)",
                (
                    RECON_SCHEMA_VERSION,
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

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
                item.coord,
                item.player,
                int(item.enabled),
                int(item.blacklisted),
                item.notes,
                item.energy,
                item.metal,
                item.minerals,
                item.gas,
                item.last_spy_at,
                item.raid_count,
                item.last_raid_at,
                item.last_return_at,
                now,
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

        ordered = sorted(
            tuple(reports),
            key=lambda item: (
                item.reported_at or datetime.min.replace(tzinfo=timezone.utc),
                item.report_id or "",
            ),
        )
        for report in ordered:
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
            if conn.execute(
                "SELECT 1 FROM recon_reports WHERE report_id=?", (report_id,)
            ).fetchone() is not None:
                duplicates.append(report_id)
                continue

            report_at = report.reported_at.astimezone(timezone.utc).isoformat()
            ingested_at = current.replace(microsecond=0).isoformat()
            with conn:
                conn.execute(
                    """INSERT INTO recon_reports(
                        report_id, target_coord, report_at, energy, metal, minerals, gas, source, ingested_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        report_id,
                        report.target,
                        report_at,
                        report.energy,
                        report.metal,
                        report.minerals,
                        report.gas,
                        report.source,
                        ingested_at,
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
                        report.target,
                        report.energy,
                        report.metal,
                        report.minerals,
                        report.gas,
                        report_at,
                        report_id,
                        ingested_at,
                    ),
                )
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
                id=int(row["id"]),
                target_coord=str(row["target_coord"]),
                report_at=str(row["report_at"]),
                energy=row["energy"],
                metal=row["metal"],
                minerals=row["minerals"],
                gas=row["gas"],
                population=None,
                ships=None,
                defense=None,
                completeness="resources",
                source=str(row["source"] or "messages"),
            )
            for row in rows
        ]

    def list_targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        rows = self.database._require_conn().execute(
            """SELECT coord, player, energy, enabled, blacklisted, notes, metal, minerals, gas,
                      last_spy_at, raid_count, last_raid_at, last_return_at
               FROM recon_targets ORDER BY coord LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [
            TargetSnapshot(
                coord=str(row["coord"]),
                player=str(row["player"] or "—"),
                energy=int(row["energy"] or 0),
                enabled=bool(row["enabled"]),
                blacklisted=bool(row["blacklisted"]),
                notes=str(row["notes"] or ""),
                metal=row["metal"],
                minerals=row["minerals"],
                gas=row["gas"],
                last_spy_at=row["last_spy_at"],
                raid_count=int(row["raid_count"] or 0),
                last_raid_at=row["last_raid_at"],
                last_return_at=row["last_return_at"],
            )
            for row in rows
        ]
