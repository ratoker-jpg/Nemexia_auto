from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nemexia_legacy_fallback_") as temp:
        profile = Path(temp)
        env = os.environ.copy()
        env.update({
            "LOCALAPPDATA": str(profile),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        })
        subprocess.run(
            ["cmd", "/d", "/c", "run_legacy.bat", "--release-smoke"],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=90,
        )
        legacy_db = profile / "NemexiaRaidManager" / "nemexia.sqlite3"
        v2_root = profile / "NemexiaRaidManagerV2"
        assert legacy_db.is_file()
        assert not v2_root.exists(), "legacy fallback must not bootstrap V2 storage"
        backups = profile / "NemexiaRaidManager" / "backups"
        assert list(backups.glob("nemexia_*.sqlite3"))
    print("release-fallback: run_legacy.bat -> app_entry.py only OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
