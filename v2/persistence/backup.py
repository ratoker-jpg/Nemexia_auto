from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from v2.persistence.database import V2Database


DEFAULT_BACKUP_KEEP = 10


def create_v2_backup(
    database: V2Database,
    backups_dir: Path,
    *,
    keep: int = DEFAULT_BACKUP_KEEP,
    now: datetime | None = None,
) -> Path:
    """Create a consistent V2 SQLite backup and retain the newest snapshots."""
    root = Path(backups_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root / f"nemexia_v2_{stamp}.sqlite3"
    suffix = 1
    while destination.exists():
        destination = root / f"nemexia_v2_{stamp}_{suffix}.sqlite3"
        suffix += 1
    database.backup_to(destination)

    retained = max(1, int(keep))
    backups = sorted(root.glob("nemexia_v2_*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
    for stale in backups[retained:]:
        stale.unlink(missing_ok=True)
    return destination
