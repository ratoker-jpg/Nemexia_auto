from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from v2.application.read_store import (
    HistorySnapshot,
    OverviewSnapshot,
    ReadOnlyStore,
    ReadStoreUnavailable,
    ReconSnapshot,
    TargetSnapshot,
)


@dataclass(frozen=True)
class DataSourceStatus:
    available: bool
    path: Path
    mode: str
    detail: str


def legacy_db_path(*, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Return the legacy SQLite location without creating any directories."""
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if os.name == "nt" or "LOCALAPPDATA" in env:
        root = Path(env.get("LOCALAPPDATA", user_home / "AppData" / "Local"))
        return root / "NemexiaRaidManager" / "nemexia.sqlite3"
    return user_home / ".nemexia_raid_manager" / "nemexia.sqlite3"


class V2ApplicationContext:
    """UI-facing read context with no storage-write or game-action APIs."""

    def __init__(self, source_path: Path) -> None:
        self.source_path = Path(source_path)
        self._store: ReadOnlyStore | None = None
        self._error: str | None = None
        try:
            self._store = ReadOnlyStore(self.source_path)
        except ReadStoreUnavailable as exc:
            self._error = str(exc)

    @classmethod
    def auto_detect(cls) -> "V2ApplicationContext":
        override = os.environ.get("NEMEXIA_V2_READ_DB", "").strip()
        source = Path(override).expanduser() if override else legacy_db_path()
        return cls(source)

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def status(self) -> DataSourceStatus:
        if self._store is None:
            return DataSourceStatus(
                available=False,
                path=self.source_path,
                mode="read-only",
                detail=self._error or "Read-only source is closed",
            )
        store_status = self._store.status()
        return DataSourceStatus(
            available=True,
            path=store_status.path,
            mode="read-only",
            detail=f"SQLite query_only={int(store_status.query_only)}",
        )

    def overview(self) -> OverviewSnapshot:
        return OverviewSnapshot() if self._store is None else self._store.overview()

    def targets(self, *, limit: int = 5000) -> list[TargetSnapshot]:
        return [] if self._store is None else self._store.list_targets(limit=limit)

    def history(self, *, limit: int = 1000) -> list[HistorySnapshot]:
        return [] if self._store is None else self._store.list_history(limit=limit)

    def recon(self, *, limit: int = 2000) -> list[ReconSnapshot]:
        return [] if self._store is None else self._store.list_recon(limit=limit)
