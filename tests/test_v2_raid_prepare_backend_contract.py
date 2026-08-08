from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "v2" / "infrastructure" / "cdp_raid_backend.py").read_text(encoding="utf-8")


def test_raid_backend_stays_attach_only() -> None:
    assert "connect_over_cdp" in SOURCE
    assert "fleets.php" in SOURCE
    assert "#ship_1_2" in SOURCE
    assert 'select_option("3")' in SOURCE
    assert "#target_c1" in SOURCE
    assert "FlyCheck" in SOURCE

    for forbidden in (
        "page.goto",
        "new_page",
        "launch_yandex",
        "BrowserWorker",
        "removeAttribute('disabled')",
    ):
        assert forbidden not in SOURCE


def test_dispatch_is_one_shot_and_verified_from_new_flight_row() -> None:
    assert "#SendFleetButton" in SOURCE
    assert "ajax_fleets.php" in SOURCE
    assert "type=SendFleet" in SOURCE
    assert SOURCE.count("await button.click()") == 1
    assert "before_ids" in SOURCE
    assert "not in before_ids" in SOURCE
    assert 'casefold() == "атака"' in SOURCE
    assert "verified=verified" in SOURCE
    assert "автоматический повтор запрещён" in SOURCE
    assert "for attempt in range" not in SOURCE


def test_backend_fails_closed_on_captcha_wrong_home_and_disabled_button() -> None:
    assert "CAPTCHA обнаружена" in SOURCE
    assert "Переключи планету вручную" in SOURCE
    assert "Игра не разрешает отправку" in SOURCE
    assert "Never Browser.close()" in SOURCE
