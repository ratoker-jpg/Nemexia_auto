from __future__ import annotations

from typing import Any

from browser import BrowserWorker


_NO_SHIPS_PHRASES = (
    "не выбраны корабли",
    "корабли не выбраны",
    "не выбрано ни одного корабля",
    "вы должны выбрать корабли",
)


def _is_no_ships_error(message: str) -> bool:
    normalized = " ".join((message or "").casefold().split())
    return any(phrase in normalized for phrase in _NO_SHIPS_PHRASES)


async def _dismiss_no_ships_popup_and_return(self: BrowserWorker, page: Any) -> bool:
    """Acknowledge the known transient popup and return to ship selection."""
    try:
        await page.locator("#dialogMessage").wait_for(state="visible", timeout=2_500)
    except Exception:
        return False

    dismissed = await page.evaluate(
        r"""() => {
            const popup = document.querySelector('#dialogMessage');
            if (!popup) return false;

            const text = (popup.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
            const known = [
                'не выбраны корабли',
                'корабли не выбраны',
                'не выбрано ни одного корабля',
                'вы должны выбрать корабли',
            ];
            if (!known.some(phrase => text.includes(phrase))) return false;

            const controls = Array.from(
                popup.querySelectorAll('input[type="button"], input[type="submit"], button, a')
            );
            const ok = popup.querySelector('#dlg_ok') || controls.find(element => {
                const label = (element.value || element.textContent || '').trim().toLowerCase();
                return label === 'ок' || label === 'ok';
            });
            if (!ok) return false;
            ok.click();

            const back = Array.from(
                document.querySelectorAll('#TabSendFleets input[type="button"], #TabSendFleets button')
            ).find(element => (element.value || element.textContent || '').trim().toLowerCase() === 'назад');
            if (back) back.click();
            else if (typeof showTab === 'function') showTab('TabChooseShips');
            else return false;
            return true;
        }"""
    )
    if not dismissed:
        return False

    try:
        await page.locator("#TabChooseShips").wait_for(state="visible", timeout=5_000)
    except Exception:
        return False
    return True


def install_ship_retry_fix() -> None:
    """Patch the legacy BrowserWorker without changing its large monolithic module."""
    BrowserWorker._is_no_ships_error = staticmethod(_is_no_ships_error)
    BrowserWorker._dismiss_no_ships_popup_and_return = _dismiss_no_ships_popup_and_return
