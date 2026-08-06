from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Nemexia Raid Manager"
APP_VERSION = "1.1.0"
GAME_HOST = "game.ares.nemexia.com"
FLEETS_URL = "https://game.ares.nemexia.com/fleets.php"
GALAXY_URL = "https://game.ares.nemexia.com/galaxy.php"
# Messages are a dynamic panel inside options.php, not a standalone page.
MESSAGES_URL = "https://game.ares.nemexia.com/options.php"


def resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        base = root / "NemexiaRaidManager"
    else:
        base = Path.home() / ".nemexia_raid_manager"
    base.mkdir(parents=True, exist_ok=True)
    return base

RESOURCE_DIR = resource_dir()
DATA_DIR = data_dir()
DB_PATH = DATA_DIR / "nemexia.sqlite3"
PROFILE_DIR = DATA_DIR / "yandex-profile"
LOG_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
BACKUP_DIR = DATA_DIR / "backups"
SEED_PATH = RESOURCE_DIR / "targets_seed.json"
ICON_PATH = RESOURCE_DIR / "assets" / "nemexia.ico"
