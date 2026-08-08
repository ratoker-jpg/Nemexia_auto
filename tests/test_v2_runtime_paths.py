from pathlib import Path

from v2.runtime_paths import build_runtime_paths, ensure_runtime_paths


def test_windows_v2_root_is_separate_from_legacy(tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    paths = build_runtime_paths(
        env={"LOCALAPPDATA": str(local_app_data)},
        platform_name="nt",
        home=tmp_path,
    )

    assert paths.root == local_app_data / "NemexiaRaidManagerV2"
    assert paths.root.name != "NemexiaRaidManager"
    assert paths.database == paths.root / "nemexia.sqlite3"
    assert paths.browser_profile == paths.root / "browser-profile"


def test_build_runtime_paths_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    paths = build_runtime_paths(env={}, platform_name="posix", home=tmp_path)
    assert paths.root == tmp_path / ".nemexia_raid_manager_v2"
    assert not paths.root.exists()


def test_ensure_runtime_paths_creates_only_v2_directories(tmp_path: Path) -> None:
    paths = build_runtime_paths(env={}, platform_name="posix", home=tmp_path)
    ensured = ensure_runtime_paths(paths)

    assert ensured is paths
    assert paths.root.is_dir()
    assert paths.browser_profile.is_dir()
    assert paths.logs.is_dir()
    assert paths.screenshots.is_dir()
    assert paths.backups.is_dir()
    assert not paths.database.exists()
