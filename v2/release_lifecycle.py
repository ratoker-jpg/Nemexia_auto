from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from v2.persistence.backup import create_v2_backup
from v2.persistence.database import V2Database
from v2.runtime_paths import RuntimePaths


class ReleaseLifecycleError(RuntimeError):
    """A production lifecycle safety gate failed before/after the Qt event loop."""


class ClosableV2Context(Protocol):
    _v2_database: V2Database | None

    def close(self) -> None: ...


ContextT = TypeVar("ContextT", bound=ClosableV2Context)
ContextFactory = Callable[[RuntimePaths], ContextT]
BackupFactory = Callable[[V2Database, Path], Path]


class V2ProductionSession:
    """Own one production Qt context plus mandatory start/stop V2 backups.

    The context factory remains responsible for schema preflight/migration and
    read-only legacy imports.  This wrapper takes the first consistent backup
    only after that bootstrap has succeeded and before the UI can run.

    Shutdown performs one more consistent backup before closing the context.
    A backup error never skips cleanup.  If the application is already failing,
    its original exception remains authoritative instead of being masked by a
    secondary shutdown-backup error.
    """

    def __init__(
        self,
        paths: RuntimePaths,
        context_factory: ContextFactory[ContextT],
        *,
        backup_factory: BackupFactory = create_v2_backup,
    ) -> None:
        self.paths = paths
        self._context_factory = context_factory
        self._backup_factory = backup_factory
        self.context: ContextT | None = None
        self.startup_backup: Path | None = None
        self.shutdown_backup: Path | None = None

    @staticmethod
    def _database(context: ClosableV2Context) -> V2Database:
        database = getattr(context, "_v2_database", None)
        if not isinstance(database, V2Database):
            raise ReleaseLifecycleError("V2 production context does not own an open V2 database")
        return database

    def __enter__(self) -> ContextT:
        context = self._context_factory(self.paths)
        self.context = context
        try:
            database = self._database(context)
            self.startup_backup = self._backup_factory(database, self.paths.backups)
        except Exception as exc:
            try:
                context.close()
            finally:
                self.context = None
            if isinstance(exc, ReleaseLifecycleError):
                raise
            raise ReleaseLifecycleError(f"V2 startup backup failed: {exc}") from exc
        return context

    def __exit__(self, exc_type, exc, tb) -> bool:
        context = self.context
        self.context = None
        if context is None:
            return False

        backup_error: Exception | None = None
        try:
            try:
                database = self._database(context)
                self.shutdown_backup = self._backup_factory(database, self.paths.backups)
            except Exception as backup_exc:  # cleanup must still run
                backup_error = backup_exc
        finally:
            context.close()

        if backup_error is not None and exc_type is None:
            raise ReleaseLifecycleError(f"V2 shutdown backup failed: {backup_error}") from backup_error
        return False
