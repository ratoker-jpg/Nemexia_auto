from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from v2 import V2_DATA_DIR_NAME


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    database: Path
    browser_profile: Path
    logs: Path
    screenshots: Path
    backups: Path


def build_runtime_paths(
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> RuntimePaths:
    """Return V2 paths without creating or touching any files.

    V2 deliberately uses a different root from the legacy Tkinter application so
    experiments cannot mutate the working database, browser profile, logs or
    backups by accident.
    """
    environment = os.environ if env is None else env
    platform = os.name if platform_name is None else platform_name
    user_home = Path.home() if home is None else Path(home)

    if platform == "nt":
        local_app_data = Path(
            environment.get("LOCALAPPDATA", str(user_home / "AppData" / "Local"))
        )
        root = local_app_data / V2_DATA_DIR_NAME
    else:
        root = user_home / ".nemexia_raid_manager_v2"

    return RuntimePaths(
        root=root,
        database=root / "nemexia.sqlite3",
        browser_profile=root / "browser-profile",
        logs=root / "logs",
        screenshots=root / "screenshots",
        backups=root / "backups",
    )


def ensure_runtime_paths(paths: RuntimePaths) -> RuntimePaths:
    """Create only the V2-owned directories and return the same path object."""
    for directory in (
        paths.root,
        paths.browser_profile,
        paths.logs,
        paths.screenshots,
        paths.backups,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths
