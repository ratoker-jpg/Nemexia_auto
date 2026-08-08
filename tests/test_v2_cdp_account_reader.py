from pathlib import Path

from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.infrastructure.cdp_read_backend import extract_coord


def test_coord_parser_handles_planet_switch_text() -> None:
    assert extract_coord("Home [ 3 : 39 : 11 ]") == "3:39:11"
    assert extract_coord("Gas [3:39:8]") == "3:39:8"


def test_account_reader_is_attach_only_and_uses_verified_legacy_selector() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "v2" / "infrastructure" / "cdp_account_reader.py").read_text(encoding="utf-8")
    legacy = (root / "browser.py").read_text(encoding="utf-8")

    assert "#planetsListHolder a" in source
    assert "#planetsListHolder a" in legacy
    assert issubclass(ReadOnlyAccountCdpBackend, object)

    for forbidden in (
        ".goto(",
        ".click(",
        ".fill(",
        ".select_option(",
        "new_page(",
        "bring_to_front(",
        "showFleets()",
        "send_raid",
        "prepare_raid",
        "request_spy",
        "delete_messages",
        "_select_planet(",
    ):
        assert forbidden not in source
