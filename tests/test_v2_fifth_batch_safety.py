from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_QT = (ROOT / "app_qt.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "v2" / "ui" / "pages" / "settings.py").read_text(encoding="utf-8")
DIAGNOSTICS = (ROOT / "v2" / "ui" / "pages" / "diagnostics.py").read_text(encoding="utf-8")
CDP = (ROOT / "v2" / "infrastructure" / "cdp_read_backend.py").read_text(encoding="utf-8")
ACCOUNT_CDP = (ROOT / "v2" / "infrastructure" / "cdp_account_reader.py").read_text(encoding="utf-8")
LEGACY_RUNNER = (ROOT / "run_app.bat").read_text(encoding="utf-8")


def test_v2_writes_are_isolated_and_legacy_launcher_is_unchanged() -> None:
    assert "V2Database(paths.database)" in APP_QT
    assert "ReadOnlyStore(source_path)" in APP_QT
    assert "LegacySettingsImporter" in APP_QT
    assert '"%VENV_PY%" app_entry.py' in LEGACY_RUNNER
    assert "app_qt.py" not in LEGACY_RUNNER
    assert "V2 SQLite" in DIAGNOSTICS
    assert "Legacy SQLite режим" in DIAGNOSTICS
    assert "context.set_v2_settings(values)" in SETTINGS


def test_fifth_batch_does_not_enable_game_actions() -> None:
    combined = "\n".join((APP_QT, SETTINGS, DIAGNOSTICS, CDP, ACCOUNT_CDP))
    for forbidden in (
        "BrowserWorker",
        "launch_yandex",
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "showFleets()",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "bring_to_front(",
    ):
        assert forbidden not in combined


def test_settings_ui_has_no_legacy_or_raw_sql_write_surface() -> None:
    for forbidden in (
        "sqlite3",
        "ReadOnlyStore",
        "legacy_setting(",
        "INSERT INTO",
        "UPDATE settings",
        "DELETE FROM",
    ):
        assert forbidden not in SETTINGS
