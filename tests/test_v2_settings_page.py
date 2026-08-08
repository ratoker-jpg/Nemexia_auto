from pathlib import Path


def test_settings_page_is_real_and_writes_only_through_v2_context() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / "v2" / "ui" / "pages" / "settings.py").read_text(encoding="utf-8")
    main = (root / "v2" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert 'if key == "settings"' in main
    assert "SettingsPage(self.context" in main
    assert "context.v2_settings_snapshot()" in page
    assert "context.set_v2_settings(values)" in page
    assert "context.set_v2_setting(" not in page
    assert "CDP port" in page
    assert "Планета автофарма" in page
    assert "Командная планета" in page
    assert "Буфер после возврата" in page

    for forbidden in (
        "ReadOnlyStore",
        "legacy_setting(",
        "sqlite3",
        "UPDATE settings",
        "INSERT INTO",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "BrowserWorker",
    ):
        assert forbidden not in page
