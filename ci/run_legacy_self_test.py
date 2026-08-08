from __future__ import annotations

import tempfile

import self_test


_ORIGINAL_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def _ci_temporary_directory(*args, **kwargs):
    """Use normal temp dirs but tolerate Windows cleanup races after tests finish.

    The legacy self-test creates SQLite backups inside a TemporaryDirectory. On
    GitHub's Windows runner the backup handle can be released just after Python
    starts directory cleanup, producing WinError 32 even though all assertions
    already passed. This harness changes cleanup behavior only for the ephemeral
    CI process; production storage/runtime code is untouched.
    """
    kwargs.setdefault("ignore_cleanup_errors", True)
    return _ORIGINAL_TEMPORARY_DIRECTORY(*args, **kwargs)


def main() -> int:
    tempfile.TemporaryDirectory = _ci_temporary_directory
    try:
        return int(self_test.main())
    finally:
        tempfile.TemporaryDirectory = _ORIGINAL_TEMPORARY_DIRECTORY


if __name__ == "__main__":
    raise SystemExit(main())
