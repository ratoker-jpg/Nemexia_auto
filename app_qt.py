from __future__ import annotations

import sys

from v2.application.asteroid_actions import AsteroidActionService
from v2.application.automatic_recon import AutomaticReconService
from v2.application.automation_context import DebrisEnabledApplicationContextWithReadiness
from v2.application.browser_read_service import V2BrowserFlightSource
from v2.application.context import V2ApplicationContext
from v2.application.debris_source import V2DebrisSource
from v2.application.legacy_settings_import import LegacySettingsImporter
from v2.application.live_bootstrap import resolve_cdp_endpoint, resolve_legacy_source_path
from v2.application.navigation import NavigationCoordinator
from v2.application.raid_actions import RaidActionService
from v2.application.read_store import ReadOnlyStore, ReadStoreUnavailable
from v2.application.recon_repository import V2ReconRepository
from v2.application.report_source import V2BrowserReportSource
from v2.application.spy_actions import SpyActionService
from v2.application.v2_queue import V2QueueRepository
from v2.application.v2_settings import V2SettingsRepository
from v2.application.asteroid_source import V2AsteroidSource
from v2.infrastructure.cdp_debris_reader import ReadOnlyDebrisCdpBackend
from v2.infrastructure.cdp_mutation_sessions import (
    V2AsteroidCdpBackendNoAutoReconnect,
    V2AutomaticReconCdpBackendNoAutoReconnect,
    V2RaidCdpBackendNoAutoReconnect,
    V2SpyCdpBackendNoAutoReconnect,
)
from v2.persistence.automatic_recon_journal import AutomaticReconJournalRepository
from v2.persistence.database import V2Database
from v2.persistence.navigation_journal import NavigationJournalRepository
from v2.release_lifecycle import ReleaseLifecycleError, V2ProductionSession
from v2.runtime_paths import RuntimePaths, build_runtime_paths, ensure_runtime_paths


def build_context(paths: RuntimePaths) -> V2ApplicationContext:
    """Build V2 with isolated writes, read-only legacy facts and explicit action gates."""
    source_path = resolve_legacy_source_path()
    database = V2Database(paths.database)
    settings = V2SettingsRepository(database)
    queue = V2QueueRepository(database)
    recon = V2ReconRepository(database)
    raid_actions: RaidActionService | None = None
    spy_actions: SpyActionService | None = None
    asteroid_actions: AsteroidActionService | None = None
    debris_source: V2DebrisSource | None = None
    navigation: NavigationCoordinator | None = None
    try:
        try:
            with ReadOnlyStore(source_path) as legacy:
                LegacySettingsImporter(legacy, settings).import_missing()
                queue.import_legacy_if_empty(legacy)
                recon.import_legacy_targets(legacy)
        except ReadStoreUnavailable:
            pass

        endpoint = resolve_cdp_endpoint(source_path, preferred_port=settings.get("cdp_port"))
        navigation_backend = V2AutomaticReconCdpBackendNoAutoReconnect(endpoint.endpoint)
        navigation = NavigationCoordinator(
            navigation_backend,
            NavigationJournalRepository(database),
        )
        automatic_recon = AutomaticReconService(
            navigation_backend,
            navigation,
            AutomaticReconJournalRepository(database),
            enabled=bool(settings.get("actions_enabled")),
        )
        spy_backend = V2SpyCdpBackendNoAutoReconnect(endpoint.endpoint)
        asteroid_backend = V2AsteroidCdpBackendNoAutoReconnect(endpoint.endpoint)
        flight_source = V2BrowserFlightSource(spy_backend)
        report_source = V2BrowserReportSource(spy_backend)
        asteroid_source = V2AsteroidSource(asteroid_backend)
        debris_source = V2DebrisSource(ReadOnlyDebrisCdpBackend(endpoint.endpoint))
        raid_actions = RaidActionService(
            V2RaidCdpBackendNoAutoReconnect(endpoint.endpoint),
            enabled=bool(settings.get("actions_enabled")),
        )
        spy_actions = SpyActionService(
            spy_backend,
            enabled=bool(settings.get("actions_enabled")),
        )
        asteroid_actions = AsteroidActionService(
            asteroid_backend,
            enabled=bool(settings.get("actions_enabled")),
        )
        return DebrisEnabledApplicationContextWithReadiness(
            source_path,
            flight_source=flight_source,
            report_source=report_source,
            v2_settings=settings,
            v2_database=database,
            v2_queue=queue,
            v2_recon=recon,
            raid_actions=raid_actions,
            spy_actions=spy_actions,
            asteroid_source=asteroid_source,
            asteroid_actions=asteroid_actions,
            debris_source=debris_source,
            navigation_coordinator=navigation,
            automatic_recon=automatic_recon,
        )
    except Exception:
        if navigation is not None:
            navigation.close()
        if debris_source is not None:
            debris_source.close()
        if asteroid_actions is not None:
            asteroid_actions.close()
        if spy_actions is not None:
            spy_actions.close()
        if raid_actions is not None:
            raid_actions.close()
        database.close()
        raise


def _lifecycle_failure(exc: ReleaseLifecycleError) -> int:
    print(f"V2 production lifecycle stopped: {exc}", file=sys.stderr)
    return 3


def release_smoke(paths: RuntimePaths) -> int:
    """Exercise the real Qt production context/lifecycle without creating a window."""
    try:
        import PySide6  # noqa: F401 - release smoke proves the installed Qt runtime exists
    except ImportError:
        print(
            "PySide6 is not installed. Install V2 dependencies with: "
            "python -m pip install -r requirements-v2.txt",
            file=sys.stderr,
        )
        return 2
    try:
        with V2ProductionSession(paths, build_context) as context:
            database = context._v2_database
            if database is None or database.integrity_check() != "ok":
                raise ReleaseLifecycleError("V2 database integrity check failed in release smoke")
        return 0
    except ReleaseLifecycleError as exc:
        return _lifecycle_failure(exc)


def main() -> int:
    """Launch the PySide6 V2 application; mutating actions remain opt-in."""
    paths = ensure_runtime_paths(build_runtime_paths())
    if "--release-smoke" in sys.argv:
        return release_smoke(paths)

    try:
        from v2.ui.main_window import run_qt_app
    except ImportError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print(
                "PySide6 is not installed. Install V2 dependencies with: "
                "python -m pip install -r requirements-v2.txt",
                file=sys.stderr,
            )
            return 2
        raise

    try:
        with V2ProductionSession(paths, build_context) as context:
            return int(run_qt_app(paths, context))
    except ReleaseLifecycleError as exc:
        return _lifecycle_failure(exc)


if __name__ == "__main__":
    raise SystemExit(main())
