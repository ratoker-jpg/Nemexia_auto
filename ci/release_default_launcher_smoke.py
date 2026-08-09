from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nemexia_qt_default_") as temp:
        profile = Path(temp)
        env = os.environ.copy()
        env.update({
            "LOCALAPPDATA": str(profile),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "QT_QPA_PLATFORM": "offscreen",
        })
        subprocess.run(
            ["cmd", "/d", "/c", "run_app.bat", "--release-smoke"],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=90,
        )

        v2_root = profile / "NemexiaRaidManagerV2"
        v2_db = v2_root / "nemexia.sqlite3"
        legacy_root = profile / "NemexiaRaidManager"
        assert v2_db.is_file()
        assert not legacy_root.exists(), "Qt default launcher must not bootstrap legacy storage"
        assert len(list((v2_root / "backups").glob("nemexia_v2_*.sqlite3"))) >= 2

        conn = sqlite3.connect(v2_db)
        try:
            assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 9
            assert str(conn.execute("PRAGMA integrity_check").fetchone()[0]) == "ok"
        finally:
            conn.close()

    print("release-default: run_app.bat -> app_qt.py only OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
