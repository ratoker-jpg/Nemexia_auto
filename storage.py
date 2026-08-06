from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from models import AsteroidObservation, CombatReport, QueueItem, SpyReport, Target, parse_dt, utc_now

PROTECTED_COORDS = frozenset({"3:2:8", "1:20:19"})


def is_protected_coord(coord: str) -> bool:
    return coord.replace(" ", "") in PROTECTED_COORDS


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS targets (
    coord TEXT PRIMARY KEY,
    player TEXT NOT NULL DEFAULT '—',
    energy INTEGER NOT NULL DEFAULT 0,
    g INTEGER NOT NULL,
    s INTEGER NOT NULL,
    p INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    blacklisted INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    last_report_at TEXT,
    metal INTEGER,
    minerals INTEGER,
    resource_gas INTEGER,
    last_spy_at TEXT,
    last_loot_total INTEGER,
    total_loot INTEGER NOT NULL DEFAULT 0,
    last_raid_at TEXT,
    last_return_at TEXT,
    raid_count INTEGER NOT NULL DEFAULT 0,
    one_way_seconds INTEGER,
    round_trip_seconds INTEGER,
    gas_needed INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fleet_id TEXT,
    source TEXT,
    target TEXT NOT NULL,
    player TEXT,
    ship_count INTEGER,
    sent_at TEXT NOT NULL,
    arrival_at TEXT,
    return_at TEXT,
    one_way_seconds INTEGER,
    round_trip_seconds INTEGER,
    gas_needed INTEGER,
    status TEXT NOT NULL DEFAULT 'sent',
    error TEXT,
    server_info TEXT,
    dedupe_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_target_sent ON history(target, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_return ON history(return_at DESC);

CREATE TABLE IF NOT EXISTS combat_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    target_coord TEXT NOT NULL,
    report_at TEXT,
    attack_at TEXT,
    result TEXT,
    metal INTEGER,
    minerals INTEGER,
    gas INTEGER,
    total_loot INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'messages',
    imported_at TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_combat_reports_target_date ON combat_reports(target_coord, report_at DESC);

CREATE TABLE IF NOT EXISTS spy_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    target_coord TEXT NOT NULL,
    report_at TEXT,
    energy INTEGER,
    metal INTEGER,
    minerals INTEGER,
    gas INTEGER,
    population INTEGER,
    ships INTEGER,
    defense INTEGER,
    completeness TEXT,
    source TEXT NOT NULL DEFAULT 'messages',
    imported_at TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_spy_reports_target_date ON spy_reports(target_coord, report_at DESC);

CREATE TABLE IF NOT EXISTS asteroid_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    coord TEXT NOT NULL,
    g INTEGER NOT NULL,
    s INTEGER NOT NULL,
    p INTEGER NOT NULL,
    last_move_server TEXT NOT NULL,
    next_move_server TEXT NOT NULL,
    period_seconds INTEGER NOT NULL,
    scanned_server_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'found',
    error TEXT,
    tooltip_html TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asteroid_scans_time ON asteroid_scans(scanned_server_at DESC);

CREATE TABLE IF NOT EXISTS asteroid_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested INTEGER NOT NULL DEFAULT 0,
    found INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    next_cycle_at TEXT
);

CREATE TABLE IF NOT EXISTS asteroid_flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    fleet_id TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    origin_coord TEXT NOT NULL,
    target_coord TEXT NOT NULL,
    source_coord TEXT NOT NULL,
    recycler_count INTEGER NOT NULL,
    shifts INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT NOT NULL,
    arrival_at TEXT,
    return_at TEXT,
    one_way_seconds INTEGER,
    round_trip_seconds INTEGER,
    gas_needed INTEGER,
    status TEXT NOT NULL DEFAULT 'sent',
    error TEXT,
    server_info TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(cycle_id) REFERENCES asteroid_cycles(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_asteroid_flights_return ON asteroid_flights(return_at DESC);
CREATE INDEX IF NOT EXISTS idx_asteroid_flights_fleet ON asteroid_flights(fleet_id);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coord TEXT NOT NULL,
    position INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(coord, state) ON CONFLICT IGNORE,
    FOREIGN KEY(coord) REFERENCES targets(coord) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_queue_state_position ON queue(state, position);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "port": 9222,
    "ship_count": 25,
    "min_energy": 7000,
    "wave_size": 15,
    "queue_size": 45,
    "max_slots": 15,
    "home_g": 3,
    "home_s": 39,
    "home_p": 11,
    "repeat_minutes": 60,
    "auto_enabled": False,
    "auto_interval_seconds": 30,
    "minimize_to_tray": True,
    "notify_returns": True,
    "confirm_single": True,
    "confirm_wave": True,
    "last_import_dir": "",
    "report_lookback_hours": 24,
    "min_metal_for_queue": 480000,
    "asteroid_home_g": 3,
    "asteroid_home_s": 39,
    "asteroid_home_p": 8,
    "asteroid_galaxy": 3,
    "asteroid_start_system": 39,
    "asteroid_end_system": 1,
    "asteroid_recyclers": 5,
    "asteroid_max_flights": 15,
    "asteroid_safety_seconds": 10,
    "asteroid_cycle_buffer_minutes": 5,
    "asteroid_auto_enabled": False,
    "asteroid_next_cycle_at": "",
}


class Database:
    def __init__(self, path: Path, seed_path: Path | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate_schema()
        self.conn.commit()
        if seed_path and self.target_count() == 0 and seed_path.exists():
            self.seed_targets(seed_path)
        self._apply_protected_targets()
        self._ensure_default_settings()

    def _apply_protected_targets(self) -> None:
        """Persistently protect coordinates which must never be selected for an attack."""
        now = utc_now().isoformat()
        with self.conn:
            for coord in PROTECTED_COORDS:
                self.conn.execute(
                    """UPDATE targets SET enabled=0, blacklisted=1,
                       notes=CASE WHEN notes='' THEN 'Исключено: нельзя атаковать' ELSE notes END,
                       updated_at=? WHERE coord=?""",
                    (now, coord),
                )

    def _migrate_schema(self) -> None:
        """Additive migration: old targets, settings and history are never removed."""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(targets)")}
        for name, declaration in {
            "last_return_at": "TEXT", "metal": "INTEGER", "minerals": "INTEGER", "resource_gas": "INTEGER",
            "last_spy_at": "TEXT", "last_loot_total": "INTEGER", "total_loot": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE targets ADD COLUMN {name} {declaration}")
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(history)")}
        if "dedupe_key" not in columns:
            self.conn.execute("ALTER TABLE history ADD COLUMN dedupe_key TEXT")
        for row in self.conn.execute(
            "SELECT id, target, arrival_at, return_at FROM history WHERE dedupe_key IS NULL OR dedupe_key=''"
        ):
            key = self._dedupe_key(dict(row))
            if key:
                self.conn.execute("UPDATE history SET dedupe_key=? WHERE id=?", (key, row["id"]))
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_history_dedupe ON history(dedupe_key)")
        # Older versions allowed the same coordinate in several queue states.
        # Keep the active send if present and discard only redundant queue rows,
        # then enforce one row per target for all future writes.
        self._dedupe_queue_rows()
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_coord_unique ON queue(coord)")
        self.conn.commit()

    def _dedupe_queue_rows(self) -> None:
        priority = {"sending": 0, "queued": 1, "failed": 2, "done": 3}
        rows = self.conn.execute(
            "SELECT id, coord, state, position FROM queue ORDER BY coord, position, id"
        ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row["coord"], []).append(row)

        duplicate_ids: list[int] = []
        retained: list[sqlite3.Row] = []
        for group in grouped.values():
            group.sort(key=lambda row: (priority.get(row["state"], 99), row["position"], row["id"]))
            retained.append(group[0])
            duplicate_ids.extend(int(row["id"]) for row in group[1:])
        if duplicate_ids:
            placeholders = ",".join("?" for _ in duplicate_ids)
            self.conn.execute(f"DELETE FROM queue WHERE id IN ({placeholders})", duplicate_ids)

        # Positions are a human-facing order. Restore a unique, consecutive
        # numbering after removing old duplicates; queued targets remain first.
        retained.sort(key=lambda row: (priority.get(row["state"], 99), row["position"], row["id"]))
        for position, row in enumerate(retained, start=1):
            if int(row["position"]) != position:
                self.conn.execute("UPDATE queue SET position=? WHERE id=?", (position, row["id"]))

    def close(self) -> None:
        self.conn.close()

    def backup(self, backup_dir: Path, keep: int = 10) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = backup_dir / f"nemexia_{stamp}.sqlite3"
        with sqlite3.connect(destination) as target:
            self.conn.backup(target)
        backups = sorted(backup_dir.glob("nemexia_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
        return destination

    def _ensure_default_settings(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        self.conn.commit()

    def seed_targets(self, seed_path: Path) -> None:
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
        now = utc_now().isoformat()
        with self.conn:
            for item in raw:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO targets(
                        coord, player, energy, g, s, p, created_at, updated_at, last_report_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["coord"], item.get("player") or "—", int(item.get("energy") or 0),
                        int(item["g"]), int(item["s"]), int(item["p"]), now, now, now,
                    ),
                )

    def target_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0])

    def get_settings(self) -> dict[str, Any]:
        values = dict(DEFAULT_SETTINGS)
        for row in self.conn.execute("SELECT key, value FROM settings"):
            try:
                values[row["key"]] = json.loads(row["value"])
            except Exception:
                values[row["key"]] = row["value"]
        return values

    def set_setting(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def set_settings(self, values: dict[str, Any]) -> None:
        with self.conn:
            for key, value in values.items():
                self.conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )

    def list_targets(self) -> list[Target]:
        rows = self.conn.execute("SELECT * FROM targets ORDER BY g, s, p").fetchall()
        return [Target.from_row(row) for row in rows]

    def get_target(self, coord: str) -> Target | None:
        row = self.conn.execute("SELECT * FROM targets WHERE coord=?", (coord,)).fetchone()
        return Target.from_row(row) if row else None

    def upsert_reports(self, reports: Iterable[SpyReport]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        now = utc_now().isoformat()
        with self.conn:
            for report in reports:
                if is_protected_coord(report.coord):
                    continue
                existing = self.conn.execute("SELECT coord FROM targets WHERE coord=?", (report.coord,)).fetchone()
                g, s, p = (int(part) for part in report.coord.split(":"))
                report_at = (report.report_at or utc_now()).isoformat()
                self.conn.execute(
                    """
                    INSERT INTO targets(
                        coord, player, energy, g, s, p, last_report_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(coord) DO UPDATE SET
                        player=excluded.player,
                        energy=excluded.energy,
                        g=excluded.g,
                        s=excluded.s,
                        p=excluded.p,
                        last_report_at=excluded.last_report_at,
                        updated_at=excluded.updated_at
                    """,
                    (report.coord, report.player or "—", int(report.energy), g, s, p, report_at, now, now),
                )
                if existing:
                    updated += 1
                else:
                    inserted += 1
        return inserted, updated

    @staticmethod
    def _message_key(kind: str, message_id: str | None, coord: str, report_at: datetime | None,
                     values: Iterable[int | None]) -> str:
        if message_id:
            return f"{kind}:id:{message_id}"
        payload = "|".join([kind, coord, report_at.isoformat() if report_at else "", *(str(v or "") for v in values)])
        return f"{kind}:fallback:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    def save_spy_reports(self, reports: Iterable[SpyReport], source: str = "messages") -> tuple[int, int, int]:
        """Keep every unique snapshot and only cache a dated newest snapshot on targets."""
        inserted = duplicates = targets_updated = 0
        now = utc_now().isoformat()
        with self.conn:
            for report in reports:
                if is_protected_coord(report.coord):
                    continue
                key = self._message_key("spy", report.message_id, report.coord, report.report_at,
                                        (report.energy, report.metal, report.minerals, report.gas))
                cur = self.conn.execute(
                    """INSERT OR IGNORE INTO spy_reports(
                        message_id,dedupe_key,target_coord,report_at,energy,metal,minerals,gas,population,ships,defense,
                        completeness,source,imported_at,raw_payload
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (report.message_id, key, report.coord, report.report_at.isoformat() if report.report_at else None,
                     report.energy, report.metal, report.minerals, report.gas, report.population, report.ships,
                     report.defense, report.completeness, source, now, report.raw_payload),
                )
                if not cur.rowcount:
                    duplicates += 1
                    continue
                inserted += 1
                if report.report_at is None:
                    continue
                g, s, p = (int(part) for part in report.coord.split(":"))
                self.conn.execute(
                    """INSERT OR IGNORE INTO targets(
                        coord,player,energy,g,s,p,last_report_at,last_spy_at,metal,minerals,resource_gas,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (report.coord, report.player or "—", report.energy, g, s, p, report.report_at.isoformat(),
                     report.report_at.isoformat(), report.metal, report.minerals, report.gas, now, now),
                )
                changed = self.conn.execute(
                    """UPDATE targets SET player=?,energy=?,metal=?,minerals=?,resource_gas=?,last_report_at=?,last_spy_at=?,updated_at=?
                       WHERE coord=? AND (last_spy_at IS NULL OR last_spy_at<=?)""",
                    (report.player or "—", report.energy, report.metal, report.minerals, report.gas,
                     report.report_at.isoformat(), report.report_at.isoformat(), now, report.coord, report.report_at.isoformat()),
                ).rowcount
                targets_updated += int(bool(changed))
        return inserted, duplicates, targets_updated

    def save_combat_reports(self, reports: Iterable[CombatReport], source: str = "messages") -> tuple[int, int, int]:
        inserted = duplicates = targets_updated = 0
        now = utc_now().isoformat()
        with self.conn:
            for report in reports:
                if is_protected_coord(report.coord):
                    continue
                key = self._message_key("combat", report.message_id, report.coord, report.report_at,
                                        (report.metal, report.minerals, report.gas))
                total = report.total_loot
                cur = self.conn.execute(
                    """INSERT OR IGNORE INTO combat_reports(
                        message_id,dedupe_key,target_coord,report_at,attack_at,result,metal,minerals,gas,total_loot,
                        source,imported_at,raw_payload
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (report.message_id, key, report.coord, report.report_at.isoformat() if report.report_at else None,
                     report.attack_at.isoformat() if report.attack_at else None, report.result, report.metal, report.minerals,
                     report.gas, total, source, now, report.raw_payload),
                )
                if not cur.rowcount:
                    duplicates += 1
                    continue
                inserted += 1
                changed = self.conn.execute(
                    """UPDATE targets SET last_loot_total=?,total_loot=total_loot+?,updated_at=?
                       WHERE coord=?""", (total, total, now, report.coord)
                ).rowcount
                targets_updated += int(bool(changed))
        return inserted, duplicates, targets_updated

    def list_spy_reports(self, limit: int = 1000) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in PROTECTED_COORDS)
        return self.conn.execute(
            f"SELECT * FROM spy_reports WHERE target_coord NOT IN ({placeholders}) ORDER BY report_at DESC, id DESC LIMIT ?",
            (*PROTECTED_COORDS, limit),
        ).fetchall()

    def list_latest_spy_reports(self, limit: int = 1000) -> list[sqlite3.Row]:
        """One most recent dated snapshot per target for the live planning view."""
        placeholders = ",".join("?" for _ in PROTECTED_COORDS)
        return self.conn.execute(
            f"""SELECT s.* FROM spy_reports s
               JOIN (SELECT target_coord, MAX(report_at) AS report_at FROM spy_reports
                     WHERE report_at IS NOT NULL AND target_coord NOT IN ({placeholders}) GROUP BY target_coord) latest
                 ON latest.target_coord=s.target_coord AND latest.report_at=s.report_at
               WHERE s.target_coord NOT IN ({placeholders})
               ORDER BY COALESCE(s.metal, -1) DESC, s.report_at DESC, s.id DESC LIMIT ?""",
            (*PROTECTED_COORDS, *PROTECTED_COORDS, limit),
        ).fetchall()

    def clear_spy_reports(self) -> int:
        """Clear local spy history and its target cache before a user-confirmed clean refresh."""
        placeholders = ",".join("?" for _ in PROTECTED_COORDS)
        rows = self.conn.execute(
            f"SELECT DISTINCT target_coord FROM spy_reports WHERE target_coord NOT IN ({placeholders})",
            tuple(PROTECTED_COORDS),
        ).fetchall()
        coords = [row["target_coord"] for row in rows]
        with self.conn:
            self.conn.execute(
                f"DELETE FROM spy_reports WHERE target_coord NOT IN ({placeholders})",
                tuple(PROTECTED_COORDS),
            )
            if coords:
                placeholders = ",".join("?" for _ in coords)
                self.conn.execute(
                    f"""UPDATE targets SET energy=0,metal=NULL,minerals=NULL,resource_gas=NULL,
                        last_report_at=NULL,last_spy_at=NULL,updated_at=?
                        WHERE coord IN ({placeholders})""", [utc_now().isoformat(), *coords]
                )
        return len(coords)

    def report_metrics(self, stale_hours: int = 24) -> dict[str, int]:
        cutoff = (utc_now() - timedelta(hours=stale_hours)).isoformat()
        row = self.conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM combat_reports) AS combats,
                (SELECT COUNT(*) FROM spy_reports) AS spies,
                SUM(CASE WHEN last_spy_at IS NOT NULL AND last_spy_at>=? THEN 1 ELSE 0 END) AS fresh,
                SUM(CASE WHEN last_spy_at IS NOT NULL AND last_spy_at<? THEN 1 ELSE 0 END) AS stale
               FROM targets""", (cutoff, cutoff)
        ).fetchone()
        return {key: int(row[key] or 0) for key in ("combats", "spies", "fresh", "stale")}

    @staticmethod
    def _asteroid_scan_key(observation: AsteroidObservation) -> str:
        payload = "|".join((
            observation.coord,
            observation.last_move_server.isoformat(),
            observation.next_move_server.isoformat(),
            observation.scanned_server_at.isoformat(),
        ))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save_asteroid_scans(self, observations: Iterable[AsteroidObservation]) -> tuple[int, int]:
        inserted = 0
        duplicates = 0
        imported_at = utc_now().isoformat()
        with self.conn:
            for observation in observations:
                key = self._asteroid_scan_key(observation)
                cur = self.conn.execute(
                    """
                    INSERT OR IGNORE INTO asteroid_scans(
                        dedupe_key, coord, g, s, p, last_move_server, next_move_server,
                        period_seconds, scanned_server_at, status, error, tooltip_html, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key, observation.coord, observation.g, observation.s, observation.p,
                        observation.last_move_server.isoformat(), observation.next_move_server.isoformat(),
                        int(observation.period_seconds), observation.scanned_server_at.isoformat(),
                        observation.status, observation.error, observation.tooltip_html, imported_at,
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    duplicates += 1
        return inserted, duplicates

    def list_latest_asteroid_scans(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT s.* FROM asteroid_scans s
            JOIN (
                SELECT coord, MAX(scanned_server_at) AS scanned_server_at
                FROM asteroid_scans GROUP BY coord
            ) latest ON latest.coord=s.coord AND latest.scanned_server_at=s.scanned_server_at
            ORDER BY s.scanned_server_at DESC, s.g, s.s DESC, s.p
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def start_asteroid_cycle(self, requested: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO asteroid_cycles(started_at, requested, status) VALUES (?, ?, 'running')",
            (utc_now().isoformat(), int(requested)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_asteroid_cycle(
        self,
        cycle_id: int,
        *,
        found: int,
        sent: int,
        status: str,
        error: str | None = None,
        next_cycle_at: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE asteroid_cycles
            SET finished_at=?, found=?, sent=?, status=?, error=?, next_cycle_at=?
            WHERE id=?
            """,
            (utc_now().isoformat(), int(found), int(sent), status, error, next_cycle_at, cycle_id),
        )
        self.conn.commit()

    @staticmethod
    def _asteroid_flight_key(result: dict[str, Any]) -> str:
        fleet_id = str(result.get("fleet_id") or "").strip()
        if fleet_id:
            return f"fleet:{fleet_id}"
        payload = "|".join(str(result.get(key) or "") for key in (
            "origin_coord", "target", "sent_at", "arrival_at", "return_at"
        ))
        return "fallback:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def add_asteroid_flight(
        self,
        result: dict[str, Any],
        *,
        cycle_id: int | None = None,
        status: str = "sent",
        error: str | None = None,
    ) -> int | None:
        key = self._asteroid_flight_key(result)
        if self.conn.execute("SELECT 1 FROM asteroid_flights WHERE dedupe_key=?", (key,)).fetchone():
            return None
        cur = self.conn.execute(
            """
            INSERT INTO asteroid_flights(
                cycle_id, fleet_id, dedupe_key, origin_coord, target_coord, source_coord,
                recycler_count, shifts, sent_at, arrival_at, return_at, one_way_seconds,
                round_trip_seconds, gas_needed, status, error, server_info, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cycle_id, result.get("fleet_id"), key, result.get("origin_coord"), result.get("target"),
                result.get("source"), int(result.get("ship_count") or 0), int(result.get("shifts") or 0),
                result.get("sent_at") or utc_now().isoformat(), result.get("arrival_at"), result.get("return_at"),
                result.get("one_way_seconds"), result.get("round_trip_seconds"), result.get("gas_needed"),
                status, error, result.get("server_info"), utc_now().isoformat(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_asteroid_flights(self, limit: int = 1000) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM asteroid_flights ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def list_asteroid_cycles(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM asteroid_cycles ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def add_target(self, coord: str, player: str, energy: int) -> None:
        g, s, p = (int(part) for part in coord.split(":"))
        now = utc_now().isoformat()
        self.conn.execute(
            """
            INSERT INTO targets(coord, player, energy, g, s, p, last_report_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coord) DO UPDATE SET player=excluded.player, energy=excluded.energy, updated_at=excluded.updated_at
            """,
            (coord, player or "—", int(energy), g, s, p, now, now, now),
        )
        self.conn.commit()
        if is_protected_coord(coord):
            self.update_target_flags(coord)

    def update_target_flags(self, coord: str, *, enabled: bool | None = None, blacklisted: bool | None = None, notes: str | None = None) -> None:
        if is_protected_coord(coord):
            enabled = False
            blacklisted = True
        fields: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            fields.append("enabled=?")
            params.append(int(enabled))
        if blacklisted is not None:
            fields.append("blacklisted=?")
            params.append(int(blacklisted))
        if notes is not None:
            fields.append("notes=?")
            params.append(notes)
        if not fields:
            return
        fields.append("updated_at=?")
        params.append(utc_now().isoformat())
        params.append(coord)
        self.conn.execute(f"UPDATE targets SET {', '.join(fields)} WHERE coord=?", params)
        self.conn.commit()

    def delete_target(self, coord: str) -> None:
        self.conn.execute("DELETE FROM targets WHERE coord=?", (coord,))
        self.conn.commit()

    def update_timing(self, coord: str, one: int, round_trip: int, gas: int | None) -> None:
        self.conn.execute(
            "UPDATE targets SET one_way_seconds=?, round_trip_seconds=?, gas_needed=?, updated_at=? WHERE coord=?",
            (one, round_trip, gas, utc_now().isoformat(), coord),
        )
        self.conn.commit()

    @staticmethod
    def _dedupe_key(result: dict[str, Any]) -> str | None:
        target = str(result.get("target") or "").replace(" ", "")
        arrival_dt = parse_dt(result.get("arrival_at"))
        return_dt = parse_dt(result.get("return_at"))
        arrival = arrival_dt.replace(microsecond=0).isoformat() if arrival_dt else str(result.get("arrival_at") or "")
        returned = return_dt.replace(microsecond=0).isoformat() if return_dt else str(result.get("return_at") or "")
        if target:
            return f"flight:{target}|{arrival}|{returned}"
        return None

    def add_history(self, result: dict[str, Any], status: str = "sent", error: str | None = None) -> int | None:
        """Persist one confirmed flight once and update its target atomically.

        A fleet ID is the primary identity; pages without one use target + arrival
        + return as a stable fallback.  An unknown send time is stored as an empty
        value and explicitly marked instead of being replaced with the current time.
        """
        dedupe_key = self._dedupe_key(result)
        fleet_id = str(result.get("fleet_id") or "").strip()
        duplicate = bool(fleet_id and self.conn.execute(
            "SELECT 1 FROM history WHERE fleet_id=? LIMIT 1", (fleet_id,)
        ).fetchone())
        # The fallback key also links a locally-sent row that did not yet expose
        # its fleet ID to a later browser synchronization that does expose it.
        if not duplicate and dedupe_key:
            duplicate = bool(self.conn.execute(
                "SELECT 1 FROM history WHERE dedupe_key=? LIMIT 1", (dedupe_key,)
            ).fetchone())
        if duplicate:
            return None
        sent_at = result.get("sent_at") or ""
        cur = self.conn.execute(
            """
            INSERT INTO history(
                fleet_id, source, target, player, ship_count, sent_at, arrival_at, return_at,
                one_way_seconds, round_trip_seconds, gas_needed, status, error, server_info, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.get("fleet_id"), result.get("source"), result.get("target"), result.get("player"),
                result.get("ship_count"), sent_at,
                result.get("arrival_at"), result.get("return_at"), result.get("one_way_seconds"),
                result.get("round_trip_seconds"), result.get("gas_needed"), status, error,
                result.get("server_info"), dedupe_key,
            ),
        )
        if status in {"sent", "unknown_time"} and result.get("target"):
            fields = ["raid_count=raid_count+1", "updated_at=?"]
            params: list[Any] = [utc_now().isoformat()]
            if sent_at:
                fields.append("last_raid_at=?")
                params.append(sent_at)
            if result.get("return_at"):
                fields.append("last_return_at=?")
                params.append(result["return_at"])
            params.append(str(result["target"]).replace(" ", ""))
            self.conn.execute(f"UPDATE targets SET {', '.join(fields)} WHERE coord=?", params)
        self.conn.commit()
        return int(cur.lastrowid)

    def sync_history_from_flights(self, flights: Iterable[Any]) -> int:
        inserted = 0
        for flight in flights:
            sent_at = None
            if flight.arrival_at and flight.return_at:
                sent_at = flight.arrival_at + (flight.arrival_at - flight.return_at)
            result = {
                "fleet_id": flight.fleet_id,
                "source": flight.source,
                "target": str(flight.target).replace(" ", ""),
                "player": flight.player,
                "sent_at": sent_at.isoformat() if sent_at else None,
                "arrival_at": flight.arrival_at.isoformat() if flight.arrival_at else None,
                "return_at": flight.return_at.isoformat() if flight.return_at else None,
            }
            status = "sent" if sent_at else "unknown_time"
            if self.add_history(result, status=status, error=None) is not None:
                inserted += 1
        return inserted

    def list_history(self, limit: int = 1000) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM history ORDER BY sent_at DESC LIMIT ?", (limit,)).fetchall()

    def last_raid_map(self) -> dict[str, datetime]:
        rows = self.conn.execute(
            "SELECT target, MAX(sent_at) AS sent_at FROM history WHERE status='sent' GROUP BY target"
        ).fetchall()
        return {row["target"]: parse_dt(row["sent_at"]) for row in rows if row["sent_at"]}

    def clear_queue(self, include_sending: bool = False) -> None:
        if include_sending:
            self.conn.execute("DELETE FROM queue")
        else:
            self.conn.execute("DELETE FROM queue WHERE state IN ('queued','failed','done')")
        self.conn.commit()

    def replace_queue(self, coords: list[str]) -> None:
        now = utc_now().isoformat()
        unique_coords = list(dict.fromkeys(coord for coord in coords if coord))
        with self.conn:
            sending = self.conn.execute(
                "SELECT id, coord FROM queue WHERE state='sending' ORDER BY position, id"
            ).fetchall()
            sending_coords = {row["coord"] for row in sending}
            self.conn.execute("DELETE FROM queue WHERE state IN ('queued','failed','done')")
            position = 0
            for coord in unique_coords:
                if coord in sending_coords:
                    continue
                position += 1
                self.conn.execute(
                    "INSERT INTO queue(coord, position, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                    (coord, position, now, now),
                )
            for row in sending:
                position += 1
                self.conn.execute("UPDATE queue SET position=? WHERE id=?", (position, row["id"]))

    def add_queue(self, coords: list[str]) -> None:
        row = self.conn.execute("SELECT COALESCE(MAX(position),0) FROM queue").fetchone()
        position = int(row[0])
        now = utc_now().isoformat()
        with self.conn:
            for coord in coords:
                exists = self.conn.execute("SELECT 1 FROM queue WHERE coord=?", (coord,)).fetchone()
                if exists:
                    continue
                position += 1
                self.conn.execute(
                    "INSERT INTO queue(coord, position, state, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                    (coord, position, now, now),
                )

    def list_queue(self, states: tuple[str, ...] = ("queued", "sending", "failed", "done")) -> list[QueueItem]:
        placeholders = ",".join("?" for _ in states)
        rows = self.conn.execute(
            f"SELECT * FROM queue WHERE state IN ({placeholders}) ORDER BY position, id", states
        ).fetchall()
        return [
            QueueItem(
                id=int(row["id"]), coord=row["coord"], position=int(row["position"]),
                state=row["state"], created_at=parse_dt(row["created_at"]),
            )
            for row in rows
        ]

    def set_queue_state(self, item_id: int, state: str) -> None:
        self.conn.execute(
            "UPDATE queue SET state=?, updated_at=? WHERE id=?",
            (state, utc_now().isoformat(), item_id),
        )
        self.conn.commit()

    def reset_stuck_sending(self, active_coords: set[str]) -> list[str]:
        """Return only non-active interrupted sends back to the ready plan state."""
        active = {coord.replace(" ", "") for coord in active_coords}
        rows = self.conn.execute("SELECT id, coord FROM queue WHERE state='sending'").fetchall()
        stale = [row for row in rows if row["coord"].replace(" ", "") not in active]
        if not stale:
            return []
        with self.conn:
            for row in stale:
                self.conn.execute(
                    "UPDATE queue SET state='queued', updated_at=? WHERE id=?",
                    (utc_now().isoformat(), row["id"]),
                )
        return [row["coord"] for row in stale]

    def remove_queue_item(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM queue WHERE id=?", (item_id,))
        self.conn.commit()

    def move_queue_item(self, item_id: int, direction: int) -> None:
        row = self.conn.execute("SELECT id, position FROM queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return
        comparator = "<" if direction < 0 else ">"
        order = "DESC" if direction < 0 else "ASC"
        other = self.conn.execute(
            f"SELECT id, position FROM queue WHERE state='queued' AND position {comparator} ? ORDER BY position {order} LIMIT 1",
            (row["position"],),
        ).fetchone()
        if not other:
            return
        with self.conn:
            self.conn.execute("UPDATE queue SET position=? WHERE id=?", (other["position"], row["id"]))
            self.conn.execute("UPDATE queue SET position=? WHERE id=?", (row["position"], other["id"]))

    def export_targets_json(self, destination: Path) -> None:
        payload = []
        for target in self.list_targets():
            payload.append({
                "coord": target.coord, "player": target.player, "energy": target.energy,
                "g": target.g, "s": target.s, "p": target.p,
                "enabled": target.enabled, "blacklisted": target.blacklisted,
                "notes": target.notes,
            })
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
