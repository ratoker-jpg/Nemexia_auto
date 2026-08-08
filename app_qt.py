from __future__ import annotations

import sys

from v2.runtime_paths import build_runtime_paths, ensure_runtime_paths


def main() -> int:
    """Launch the isolated PySide6 preview without touching legacy runtime data."""
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
    return int(run_qt_app(paths))


if __name__ == "__main__":
    raise SystemExit(main())
