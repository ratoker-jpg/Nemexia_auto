from __future__ import annotations

import sys

from v2.application.browser_read_service import V2BrowserFlightSource
from v2.application.context import V2ApplicationContext
from v2.application.live_bootstrap import resolve_cdp_endpoint, resolve_legacy_source_path
from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.runtime_paths import build_runtime_paths, ensure_runtime_paths


def build_context() -> V2ApplicationContext:
    """Build V2 with read-only SQLite plus attach-only live browser facts."""
    source_path = resolve_legacy_source_path()
    endpoint = resolve_cdp_endpoint(source_path)
    backend = ReadOnlyAccountCdpBackend(endpoint.endpoint)
    flight_source = V2BrowserFlightSource(backend)
    return V2ApplicationContext(source_path, flight_source=flight_source)


def main() -> int:
    """Launch the PySide6 preview without enabling game actions."""
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
    context = build_context()
    try:
        return int(run_qt_app(paths, context))
    finally:
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
