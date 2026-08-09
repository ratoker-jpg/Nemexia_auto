from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import Database


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


def _connect_v2(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _assert_v2_integrity(path: Path) -> None:
    conn = _connect_v2(path)
    try:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 9
        assert str(conn.execute("PRAGMA integrity_check").fetchone()[0]) == "ok"
    finally:
        conn.close()


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

    _run_entry("app_qt.py", profile)
    assert v2_db.is_file()
    assert not legacy_db.exists()
    _assert_v2_integrity(v2_db)
    assert len(list((v2_root / "backups").glob("nemexia_v2_*.sqlite3"))) >= 2

    v2_before_legacy = v2_db.read_bytes()
    _run_entry("app_entry.py", profile)
    assert legacy_db.is_file()
    assert v2_db.read_bytes() == v2_before_legacy
    assert list((legacy_root / "backups").glob("nemexia_*.sqlite3"))

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


def _read_v2_release_facts(path: Path) -> tuple[dict[str, str], int, int]:
    conn = _connect_v2(path)
    try:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 9
        assert str(conn.execute("PRAGMA integrity_check").fetchone()[0]) == "ok"
        settings = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM settings").fetchall()
        }
        queue_count = int(conn.execute("SELECT COUNT(*) FROM raid_queue").fetchone()[0])
        recon_count = int(conn.execute("SELECT COUNT(*) FROM recon_targets").fetchone()[0])
        return settings, queue_count, recon_count
    finally:
        conn.close()


def _set_v2_return_buffer(path: Path, value: int) -> None:
    conn = _connect_v2(path)
    try:
        with conn:
            conn.execute(
                "UPDATE settings SET value=? WHERE key='farm_return_buffer_minutes'",
                (str(value),),
            )
    finally:
        conn.close()


def _existing_user_upgrade(profile: Path) -> None:
    legacy_db, legacy_before_qt = _seed_existing_user(profile)
    v2_root = _v2_root(profile)
    v2_db = v2_root / "nemexia.sqlite3"

    assert not v2_db.exists()
    _run_entry("app_qt.py", profile)

    assert legacy_db.read_bytes() == legacy_before_qt
    assert v2_db.is_file()
    settings, queue_count, recon_count = _read_v2_release_facts(v2_db)
    assert settings["cdp_port"] == "9333"
    assert settings["farm_home"] == "3:39:11"
    assert settings["farm_return_buffer_minutes"] == "7"
    assert queue_count == 5
    assert recon_count > 0
    _set_v2_return_buffer(v2_db, 9)

    _run_entry("app_qt.py", profile)
    assert legacy_db.read_bytes() == legacy_before_qt
    settings, queue_count, _ = _read_v2_release_facts(v2_db)
    assert settings["farm_return_buffer_minutes"] == "9"
    assert queue_count == 5

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
