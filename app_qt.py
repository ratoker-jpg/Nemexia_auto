from __future__ import annotations

import sys

from v2.application.context import V2ApplicationContext
from v2.runtime_paths import build_runtime_paths, ensure_runtime_paths


def main() -> int:
    """Launch the PySide6 preview with read-only access to legacy data."""
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
    context = V2ApplicationContext.auto_detect()
    try:
        return int(run_qt_app(paths, context))
    finally:
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
