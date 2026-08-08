from __future__ import annotations

import sys

from v2.application.asteroid_actions import AsteroidActionService
from v2.application.asteroid_context import AsteroidEnabledApplicationContext
from v2.application.asteroid_source import V2AsteroidSource
from v2.application.browser_read_service import V2BrowserFlightSource
from v2.application.context import V2ApplicationContext
from v2.application.legacy_settings_import import LegacySettingsImporter
from v2.application.live_bootstrap import resolve_cdp_endpoint, resolve_legacy_source_path
from v2.application.raid_actions import RaidActionService
from v2.application.read_store import ReadOnlyStore, ReadStoreUnavailable
from v2.application.recon_repository import V2ReconRepository
from v2.application.report_source import V2BrowserReportSource
from v2.application.spy_actions import SpyActionService
from v2.application.v2_queue import V2QueueRepository
from v2.application.v2_settings import V2SettingsRepository
from v2.infrastructure.cdp_asteroid_backend import V2AsteroidCdpBackend
from v2.infrastructure.cdp_raid_backend import V2RaidCdpBackend
from v2.infrastructure.cdp_spy_backend import V2SpyCdpBackend
from v2.persistence.database import V2Database
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
    try:
        try:
            with ReadOnlyStore(source_path) as legacy:
                LegacySettingsImporter(legacy, settings).import_missing()
                queue.import_legacy_if_empty(legacy)
                recon.import_legacy_targets(legacy)
        except ReadStoreUnavailable:
            pass

        endpoint = resolve_cdp_endpoint(source_path, preferred_port=settings.get("cdp_port"))
        spy_backend = V2SpyCdpBackend(endpoint.endpoint)
        asteroid_backend = V2AsteroidCdpBackend(endpoint.endpoint)
        flight_source = V2BrowserFlightSource(spy_backend)
        report_source = V2BrowserReportSource(spy_backend)
        asteroid_source = V2AsteroidSource(asteroid_backend)
        raid_actions = RaidActionService(
            V2RaidCdpBackend(endpoint.endpoint),
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
        return AsteroidEnabledApplicationContext(
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
        )
    except Exception:
        if asteroid_actions is not None:
            asteroid_actions.close()
        if spy_actions is not None:
            spy_actions.close()
        if raid_actions is not None:
            raid_actions.close()
        database.close()
        raise


def main() -> int:
    """Launch the PySide6 V2 application; mutating actions remain opt-in."""
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

    paths = ensure_runtime_paths(build_runtime_paths())
    context = build_context(paths)
    try:
        return int(run_qt_app(paths, context))
    finally:
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
