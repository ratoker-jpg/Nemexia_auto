from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import Database
from v2.application.v2_settings import V2SettingsRepository
from v2.persistence.database import V2Database


SEED = ROOT / "targets_seed.json"


def _legacy_root(profile: Path) -> Path:
    return profile / "NemexiaRaidManager"


def _v2_root(profile: Path) -> Path:
    return profile / "NemexiaRaidManagerV2"


def _run_entry(entry: str, profile: Path) -> None:
    env = os.environ.copy()
    env.update({
        "LOCALAPPDATA": str(profile),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "QT_QPA_PLATFORM": "offscreen",
    })
    subprocess.run(
        [sys.executable, str(ROOT / entry), "--release-smoke"],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=90,
    )


def _assert_v2_integrity(path: Path) -> None:
    with V2Database(path) as database:
        assert database.schema_version() == 9
        assert database.integrity_check() == "ok"


def _assert_db_unlocked(path: Path, *, timeout_seconds: float = 5.0) -> None:
    """Require Windows to release the SQLite file handle within a bounded window."""
    probe = path.with_name(path.name + ".unlock-check")
    assert not probe.exists()
    deadline = time.monotonic() + timeout_seconds
    last_error: PermissionError | None = None
    while time.monotonic() < deadline:
        try:
            os.replace(path, probe)
            os.replace(probe, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"SQLite file remained locked after {timeout_seconds}s: {path}") from last_error


def _clean_install(profile: Path) -> None:
    legacy_root = _legacy_root(profile)
    legacy_db = legacy_root / "nemexia.sqlite3"
    v2_root = _v2_root(profile)
    v2_db = v2_root / "nemexia.sqlite3"

    assert not legacy_root.exists() and not v2_root.exists()

    # Qt must be able to bootstrap an empty user profile without creating or
    # mutating the legacy storage root.
    _run_entry("app_qt.py", profile)
    assert v2_db.is_file()
    assert not legacy_db.exists()
    _assert_v2_integrity(v2_db)
    assert len(list((v2_root / "backups").glob("nemexia_v2_*.sqlite3"))) >= 2

    # The legacy smoke then creates only its own root. It must not touch the
    # already-created V2 database.
    v2_before_legacy = v2_db.read_bytes()
    _run_entry("app_entry.py", profile)
    assert legacy_db.is_file()
    assert v2_db.read_bytes() == v2_before_legacy
    assert list((legacy_root / "backups").glob("nemexia_*.sqlite3"))

    # Once both roots exist, Qt can start again and remain isolated from the
    # legacy database bytes even while importing accepted facts read-only.
    legacy_before_qt = legacy_db.read_bytes()
    _run_entry("app_qt.py", profile)
    assert legacy_db.read_bytes() == legacy_before_qt
    _assert_v2_integrity(v2_db)
    assert legacy_root.resolve() != v2_root.resolve()
    _assert_db_unlocked(legacy_db)
    _assert_db_unlocked(v2_db)


def _seed_existing_user(profile: Path) -> tuple[Path, bytes]:
    legacy_db = _legacy_root(profile) / "nemexia.sqlite3"
    _run_entry("app_entry.py", profile)

    database = Database(legacy_db, SEED)
    try:
        database.set_setting("port", 9333)
        database.set_setting("home_g", 3)
        database.set_setting("home_s", 39)
        database.set_setting("home_p", 11)
        database.set_setting("farm_return_buffer_minutes", 7)
        eligible = [
            target.coord for target in database.list_targets()
            if target.enabled and not target.blacklisted
        ][:5]
        assert len(eligible) == 5
        database.replace_queue(eligible)
    finally:
        database.close()
    return legacy_db, legacy_db.read_bytes()


def _existing_user_upgrade(profile: Path) -> None:
    legacy_db, legacy_before_qt = _seed_existing_user(profile)
    v2_root = _v2_root(profile)
    v2_db = v2_root / "nemexia.sqlite3"

    assert not v2_db.exists()
    _run_entry("app_qt.py", profile)

    # V2 imports through mode=ro/query_only; the source database must stay
    # byte-for-byte identical.
    assert legacy_db.read_bytes() == legacy_before_qt
    assert v2_db.is_file()
    with V2Database(v2_db) as database:
        assert database.schema_version() == 9
        assert database.integrity_check() == "ok"
        settings = V2SettingsRepository(database)
        assert settings.get("cdp_port") == 9333
        assert settings.get("farm_home") == "3:39:11"
        assert settings.get("farm_return_buffer_minutes") == 7
        assert len(database.list_raid_queue_rows()) == 5
        assert len(database.list_recon_target_rows()) > 0
        settings.set("farm_return_buffer_minutes", 9)

    # Restart preserves V2-owned state and must still leave legacy bytes alone.
    _run_entry("app_qt.py", profile)
    assert legacy_db.read_bytes() == legacy_before_qt
    with V2Database(v2_db) as database:
        settings = V2SettingsRepository(database)
        assert settings.get("farm_return_buffer_minutes") == 9
        assert len(database.list_raid_queue_rows()) == 5
        assert database.integrity_check() == "ok"

    # The original Tkinter runtime remains independently startable against its
    # own primary DB after the Qt upgrade path exists.
    _run_entry("app_entry.py", profile)
    assert legacy_db.is_file()
    assert v2_db.is_file()
    _assert_v2_integrity(v2_db)
    _assert_db_unlocked(legacy_db)
    _assert_db_unlocked(v2_db)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nemexia_release_side_by_side_") as temp:
        root = Path(temp)
        _clean_install(root / "clean")
        _existing_user_upgrade(root / "upgrade")
    print("release-side-by-side: clean install + existing-user upgrade OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
