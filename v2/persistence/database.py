from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


V2_SCHEMA_VERSION = 7


class V2DatabaseError(RuntimeError):
    pass


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _preflight_existing_schema(path: Path) -> None:
    if not path.exists():
        return
    try:
        with sqlite3.connect(_readonly_uri(path), uri=True) as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        raise V2DatabaseError(f"Cannot open existing V2 database read-only: {path}") from exc
    if current > V2_SCHEMA_VERSION:
        raise V2DatabaseError(
            f"V2 database schema {current} is newer than supported {V2_SCHEMA_VERSION}"
        )


class V2Database:
    """Own the isolated V2 SQLite database and its schema migrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        _preflight_existing_schema(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            self._migrate()
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            self._conn.close()
            raise

    def __enter__(self) -> "V2Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise V2DatabaseError("V2 database is closed")
        return self._conn

    def schema_version(self) -> int:
        return int(self._require_conn().execute("PRAGMA user_version").fetchone()[0])

    def integrity_check(self) -> str:
        return str(self._require_conn().execute("PRAGMA integrity_check").fetchone()[0])

    def backup_to(self, destination: Path) -> Path:
        conn = self._require_conn()
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_conn = sqlite3.connect(target)
        try:
            conn.backup(backup_conn)
            backup_conn.commit()
        finally:
            backup_conn.close()
        return target

    def table_names(self) -> frozenset[str]:
        rows = self._require_conn().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return frozenset(str(row[0]) for row in rows)

    def read_setting_raw(self, key: str) -> str | None:
        row = self._require_conn().execute("SELECT value FROM settings WHERE key=?", (str(key),)).fetchone()
        return str(row[0]) if row is not None else None

    def write_setting_raw(self, key: str, value: str) -> None:
        self.write_settings_raw({str(key): str(value)})

    def write_settings_raw(self, values: Mapping[str, str]) -> None:
        conn = self._require_conn()
        if not values:
            return
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = [(str(key), str(value), now) for key, value in values.items()]
        with conn:
            conn.executemany(
                """
                INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                rows,
            )

    def read_all_settings_raw(self) -> dict[str, str]:
        rows = self._require_conn().execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def begin_raid_action(self, *, request_id: str, source: str, target: str, player: str, ship_count: int) -> None:
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO raid_actions(
                        request_id, source, target, player, ship_count, status, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (str(request_id), str(source), str(target), str(player), int(ship_count), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(f"Raid request already exists: {request_id}") from exc

    def finish_raid_action(
        self, request_id: str, *, status: str, fleet_id: str | None = None,
        sent_at: str | None = None, arrival_at: str | None = None,
        return_at: str | None = None, detail: str = "",
    ) -> None:
        allowed = {"verified", "ambiguous", "rejected", "failed"}
        if status not in allowed:
            raise V2DatabaseError(f"Invalid raid action status: {status}")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                """UPDATE raid_actions SET status=?, fleet_id=?, sent_at=?, arrival_at=?, return_at=?,
                   detail=?, updated_at=? WHERE request_id=? AND status='pending'""",
                (status, fleet_id, sent_at, arrival_at, return_at, str(detail or ""), now, str(request_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending raid request not found: {request_id}")

    def resolve_raid_action(
        self, request_id: str, *, fleet_id: str, sent_at: str | None = None,
        arrival_at: str | None = None, return_at: str | None = None,
        detail: str = "live-flight reconciliation",
    ) -> None:
        if not str(fleet_id or "").strip():
            raise V2DatabaseError("fleet_id is required to resolve a raid action")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                """UPDATE raid_actions
                   SET status='verified', fleet_id=?, sent_at=COALESCE(sent_at, ?),
                       arrival_at=COALESCE(arrival_at, ?), return_at=COALESCE(return_at, ?),
                       detail=?, updated_at=?
                 WHERE request_id=? AND status IN ('pending','ambiguous')""",
                (str(fleet_id), sent_at, arrival_at, return_at, str(detail or ""), now, str(request_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Unresolved raid request not found: {request_id}")

    def read_raid_action(self, request_id: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            "SELECT * FROM raid_actions WHERE request_id=?", (str(request_id),)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_raid_actions(self, *, limit: int = 200) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            "SELECT * FROM raid_actions ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def unresolved_raid_action(self, *, source: str, target: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            """SELECT * FROM raid_actions WHERE source=? AND target=?
               AND status IN ('pending','ambiguous') ORDER BY id DESC LIMIT 1""",
            (str(source), str(target)),
        ).fetchone()
        return dict(row) if row is not None else None

    def begin_spy_action(self, *, request_id: str, fleet_id: str, source: str, target: str) -> None:
        """Persist immutable exact-fleet intent before one remote processSpy attempt."""
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO spy_actions(
                        request_id, fleet_id, source, target, status, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, 'pending', ?, ?)""",
                    (str(request_id), str(fleet_id), str(source), str(target), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise V2DatabaseError(
                f"Spy request conflicts with an existing request or unresolved fleet: {request_id}"
            ) from exc

    def finish_spy_action(
        self, request_id: str, *, status: str, report_id: str | None = None,
        requested_at: str | None = None, report_at: str | None = None, detail: str = "",
    ) -> None:
        allowed = {"verified", "ambiguous", "failed_safe"}
        if status not in allowed:
            raise V2DatabaseError(f"Invalid spy action status: {status}")
        if status == "verified" and (not str(report_id or "").strip() or not str(report_at or "").strip()):
            raise V2DatabaseError("Verified spy action requires report_id and report_at")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                """UPDATE spy_actions
                   SET status=?, report_id=?, requested_at=?, report_at=?, detail=?, updated_at=?
                 WHERE request_id=? AND status='pending'""",
                (status, report_id, requested_at, report_at, str(detail or ""), now, str(request_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Pending spy request not found: {request_id}")

    def resolve_spy_action(
        self, request_id: str, *, report_id: str, report_at: str,
        detail: str = "fresh-report reconciliation",
    ) -> None:
        if not str(report_id or "").strip() or not str(report_at or "").strip():
            raise V2DatabaseError("report_id and report_at are required to resolve a spy action")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                """UPDATE spy_actions
                   SET status='verified', report_id=?, report_at=?, detail=?, updated_at=?
                 WHERE request_id=? AND status IN ('pending','ambiguous')""",
                (str(report_id), str(report_at), str(detail or ""), now, str(request_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Unresolved spy request not found: {request_id}")

    def read_spy_action(self, request_id: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            "SELECT * FROM spy_actions WHERE request_id=?", (str(request_id),)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_spy_actions(self, *, limit: int = 200) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            "SELECT * FROM spy_actions ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def unresolved_spy_action(self, *, fleet_id: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            """SELECT * FROM spy_actions WHERE fleet_id=?
               AND status IN ('pending','ambiguous') ORDER BY id DESC LIMIT 1""",
            (str(fleet_id),),
        ).fetchone()
        return dict(row) if row is not None else None

    def unresolved_spy_target(self, *, source: str, target: str) -> dict[str, object] | None:
        row = self._require_conn().execute(
            """SELECT * FROM spy_actions WHERE source=? AND target=?
               AND status IN ('pending','ambiguous') ORDER BY id DESC LIMIT 1""",
            (str(source), str(target)),
        ).fetchone()
        return dict(row) if row is not None else None

    def raid_queue_count(self) -> int:
        return int(self._require_conn().execute("SELECT COUNT(*) FROM raid_queue").fetchone()[0])

    def import_raid_queue_rows(self, rows: Sequence[Mapping[str, object]]) -> int:
        """Seed V2 queue exactly once; never overwrite an existing V2 queue."""
        conn = self._require_conn()
        if self.raid_queue_count() or not rows:
            return 0
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = [(
            int(row["legacy_id"]), int(row["position"]), str(row["state"]), str(row["coord"]),
            str(row.get("player") or "—"), row.get("metal"), row.get("minerals"), row.get("gas"),
            row.get("last_spy_at"), int(bool(row.get("enabled", True))),
            int(bool(row.get("blacklisted", False))), now, now,
        ) for row in rows]
        with conn:
            conn.executemany(
                """INSERT INTO raid_queue(
                    imported_legacy_id, position, state, coord, player, metal, minerals, gas,
                    last_spy_at, enabled, blacklisted, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                payload,
            )
        return len(payload)

    def list_raid_queue_rows(self, *, limit: int = 5000) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            """SELECT * FROM raid_queue
               ORDER BY CASE WHEN state='queued' THEN 0 ELSE 1 END, position, id LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_raid_queue_state(self, queue_id: int, state: str) -> None:
        state = str(state).strip()
        if state not in {"queued", "sending", "sent", "ambiguous", "failed", "skipped"}:
            raise V2DatabaseError(f"Invalid raid queue state: {state}")
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with conn:
            cursor = conn.execute(
                "UPDATE raid_queue SET state=?, updated_at=? WHERE id=?",
                (state, now, int(queue_id)),
            )
        if cursor.rowcount != 1:
            raise V2DatabaseError(f"Raid queue row not found: {queue_id}")

    def import_recon_target_rows(self, rows: Sequence[Mapping[str, object]]) -> int:
        """Seed only missing V2 target metadata from read-only legacy input."""
        if not rows:
            return 0
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        unique: dict[str, Mapping[str, object]] = {}
        for row in rows:
            coord = str(row.get("coord") or "").strip()
            if coord:
                unique.setdefault(coord, row)
        payload = [
            (
                coord,
                str(row.get("player") or "—"),
                int(bool(row.get("enabled", True))),
                int(bool(row.get("blacklisted", False))),
                str(row.get("notes") or ""),
                now,
                now,
            )
            for coord, row in unique.items()
        ]
        with conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO recon_targets(
                    coord, player, enabled, blacklisted, notes, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?)""",
                payload,
            )
            return conn.total_changes - before

    def insert_recon_report_rows(self, rows: Sequence[Mapping[str, object]]) -> int:
        """Persist immutable report snapshots and ensure every report has a V2 target row."""
        if not rows:
            return 0
        conn = self._require_conn()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        targets = sorted({str(row["target"]) for row in rows})
        with conn:
            conn.executemany(
                """INSERT OR IGNORE INTO recon_targets(
                    coord, player, enabled, blacklisted, notes, created_at, updated_at
                ) VALUES(?, '—', 1, 0, '', ?, ?)""",
                [(coord, now, now) for coord in targets],
            )
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO recon_reports(
                    report_id, target, report_at, energy, metal, minerals, gas, source, ingested_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        str(row["report_id"]),
                        str(row["target"]),
                        str(row["report_at"]),
                        row.get("energy"),
                        row.get("metal"),
                        row.get("minerals"),
                        row.get("gas"),
                        str(row.get("source") or "messages"),
                        now,
                    )
                    for row in rows
                ],
            )
            return conn.total_changes - before

    def list_recon_report_rows(self, *, limit: int = 2000) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            """SELECT id, report_id, target, report_at, energy, metal, minerals, gas, source, ingested_at
               FROM recon_reports
               ORDER BY report_at DESC, report_id DESC, id DESC
               LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_recon_target_rows(self, *, limit: int = 5000) -> list[dict[str, object]]:
        rows = self._require_conn().execute(
            """SELECT t.coord, t.player, t.enabled, t.blacklisted, t.notes,
                      r.report_id, r.report_at, r.energy, r.metal, r.minerals, r.gas
               FROM recon_targets t
               LEFT JOIN recon_reports r ON r.id = (
                   SELECT rr.id FROM recon_reports rr
                    WHERE rr.target=t.coord
                    ORDER BY rr.report_at DESC, rr.report_id DESC, rr.id DESC
                    LIMIT 1
               )
               ORDER BY t.coord
               LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _migrate(self) -> None:
        current = self.schema_version()
        if current > V2_SCHEMA_VERSION:
            raise V2DatabaseError(f"V2 database schema {current} is newer than supported {V2_SCHEMA_VERSION}")
        while current < V2_SCHEMA_VERSION:
            next_version = current + 1
            migration = getattr(self, f"_migrate_to_{next_version}", None)
            if not callable(migration):
                raise V2DatabaseError(f"Missing V2 migration {current} -> {next_version}")
            with self._require_conn():
                migration()
                self._require_conn().execute(f"PRAGMA user_version={next_version}")
            current = next_version

    def _record_migration(self, version: int) -> None:
        self._require_conn().execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (int(version), datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
        )

    def _migrate_to_1(self) -> None:
        self._require_conn().executescript(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            );"""
        )
        self._record_migration(1)

    def _migrate_to_2(self) -> None:
        self._require_conn().executescript(
            """CREATE TABLE IF NOT EXISTS raid_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL, target TEXT NOT NULL, player TEXT NOT NULL,
                ship_count INTEGER NOT NULL CHECK(ship_count > 0),
                status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','rejected','failed')),
                fleet_id TEXT, sent_at TEXT, arrival_at TEXT, return_at TEXT,
                detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_raid_actions_target_status
                ON raid_actions(source, target, status);"""
        )
        self._record_migration(2)

    def _migrate_to_3(self) -> None:
        self._require_conn().executescript(
            """CREATE TABLE IF NOT EXISTS raid_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imported_legacy_id INTEGER UNIQUE,
                position INTEGER NOT NULL,
                state TEXT NOT NULL,
                coord TEXT NOT NULL,
                player TEXT NOT NULL,
                metal INTEGER, minerals INTEGER, gas INTEGER,
                last_spy_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                blacklisted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_raid_queue_state_position
                ON raid_queue(state, position, id);"""
        )
        self._record_migration(3)

    def _migrate_to_4(self) -> None:
        self._require_conn().executescript(
            """CREATE TABLE IF NOT EXISTS spy_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                probe_count INTEGER NOT NULL CHECK(probe_count > 0),
                probe_ship_key TEXT NOT NULL,
                available_probes INTEGER NOT NULL CHECK(available_probes >= 0),
                status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','failed_safe')),
                report_id TEXT,
                requested_at TEXT,
                report_at TEXT,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_spy_actions_target_status
                ON spy_actions(source, target, status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_spy_actions_unresolved_target
                ON spy_actions(source, target)
                WHERE status IN ('pending','ambiguous');"""
        )
        self._record_migration(4)

    def _migrate_to_5(self) -> None:
        """Atomically correct the unproven probe model to exact spy-fleet identity."""
        conn = self._require_conn()
        # executescript() would implicitly commit before running its script. Start
        # one explicit transaction and use individual execute() calls so the table
        # rebuild, migration record and caller's PRAGMA user_version=5 commit or
        # roll back together.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP INDEX IF EXISTS idx_spy_actions_target_status")
        conn.execute("DROP INDEX IF EXISTS idx_spy_actions_unresolved_target")
        conn.execute("ALTER TABLE spy_actions RENAME TO spy_actions_v4")
        conn.execute(
            """CREATE TABLE spy_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                fleet_id TEXT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','verified','ambiguous','failed_safe')),
                report_id TEXT,
                requested_at TEXT,
                report_at TEXT,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO spy_actions(
                id, request_id, fleet_id, source, target, status, report_id,
                requested_at, report_at, detail, created_at, updated_at
            )
            SELECT id, request_id, NULL, source, target, status, report_id,
                   requested_at, report_at,
                   CASE
                     WHEN detail='' THEN 'migrated from V2 schema 4: fleet_id was not recorded'
                     ELSE detail || ' | migrated from V2 schema 4: fleet_id was not recorded'
                   END,
                   created_at, updated_at
              FROM spy_actions_v4"""
        )
        conn.execute("DROP TABLE spy_actions_v4")
        conn.execute(
            "CREATE INDEX idx_spy_actions_target_status ON spy_actions(source, target, status)"
        )
        conn.execute(
            """CREATE UNIQUE INDEX idx_spy_actions_unresolved_fleet
               ON spy_actions(fleet_id)
               WHERE fleet_id IS NOT NULL AND status IN ('pending','ambiguous')"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX idx_spy_actions_unresolved_target
               ON spy_actions(source, target)
               WHERE status IN ('pending','ambiguous')"""
        )
        self._record_migration(5)

    def _migrate_to_6(self) -> None:
        """Add V2-owned immutable reconnaissance snapshots and target metadata."""
        self._require_conn().executescript(
            """CREATE TABLE IF NOT EXISTS recon_targets (
                coord TEXT PRIMARY KEY,
                player TEXT NOT NULL DEFAULT '—',
                enabled INTEGER NOT NULL DEFAULT 1,
                blacklisted INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recon_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                target TEXT NOT NULL,
                report_at TEXT NOT NULL,
                energy INTEGER,
                metal INTEGER,
                minerals INTEGER,
                gas INTEGER,
                source TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                UNIQUE(report_id, target, report_at),
                FOREIGN KEY(target) REFERENCES recon_targets(coord)
            );
            CREATE INDEX IF NOT EXISTS idx_recon_reports_target_time
                ON recon_reports(target, report_at DESC, report_id DESC);
            CREATE INDEX IF NOT EXISTS idx_recon_reports_time
                ON recon_reports(report_at DESC, report_id DESC);"""
        )
        self._record_migration(6)

    def _migrate_to_7(self) -> None:
        """Add V2-owned persistent asteroid dispatch identity/recovery journal."""
        # Local import avoids a module cycle at import time: asteroid_journal uses
        # V2Database only for its repository type, while this hook owns migration.
        from v2.persistence.asteroid_journal import install_asteroid_journal_schema

        install_asteroid_journal_schema(self._require_conn())
        self._record_migration(7)
