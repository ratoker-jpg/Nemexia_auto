from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "v2" / "infrastructure" / "cdp_raid_backend.py").read_text(encoding="utf-8")


def test_prepare_backend_is_attach_only_and_has_no_send_surface() -> None:
    assert "connect_over_cdp" in SOURCE
    assert "fleets.php" in SOURCE
    assert "#ship_1_2" in SOURCE
    assert 'select_option("3")' in SOURCE
    assert "#target_c1" in SOURCE
    assert "FlyCheck" in SOURCE

    for forbidden in (
        "#SendFleetButton",
        "type=SendFleet",
        "ajax_fleets.php",
        ".click()",
        "page.goto",
        "new_page",
        "launch_yandex",
        "BrowserWorker",
    ):
        assert forbidden not in SOURCE


def test_prepare_backend_fails_closed_on_captcha_and_wrong_home() -> None:
    assert "CAPTCHA обнаружена" in SOURCE
    assert "Переключи планету вручную" in SOURCE
    assert "V2 dispatch is not enabled yet" in SOURCE
    assert "Never Browser.close()" in SOURCE
