from __future__ import annotations

from typing import Any

from browser import BrowserAutomationError


_INSTALLED_CLASSES: set[type[Any]] = set()


async def _read_fleet_capacity_with_settings_fallback(self: Any) -> dict[str, int]:
    """Read current fleet usage from Nemexia and tolerate a broken DOM max counter.

    `used` must come from the live game page. The maximum is read from the game
    when possible, but if Nemexia exposes a stale/zero `#MaxFleets` node the
    configured application value is used instead. This prevents a valid setting
    such as 22 from being discarded merely because one DOM selector returned 0.
    """
    page = await self._ensure_fleets_page()
    values = await page.evaluate(
        r"""() => {
            const numbers = (selector) => Array.from(document.querySelectorAll(selector))
                .map((node) => Number.parseInt((node.textContent || '').replace(/\s+/g, ''), 10))
                .filter((value) => Number.isFinite(value));

            const body = document.body?.innerText || '';
            const match = body.match(/Пол[её]ты\s*:\s*(\d+)\s*\/\s*Макс\.?\s*флота\s*:\s*(\d+)/i);

            return {
                usedCandidates: numbers('#FleetsCount'),
                maxCandidates: numbers('#MaxFleets'),
                textUsed: match ? Number.parseInt(match[1], 10) : null,
                textMax: match ? Number.parseInt(match[2], 10) : null,
            };
        }"""
    )

    used_candidates = [int(value) for value in (values.get("usedCandidates") or [])]
    max_candidates = [int(value) for value in (values.get("maxCandidates") or [])]

    text_used = values.get("textUsed")
    text_max = values.get("textMax")

    if text_used is not None:
        used = int(text_used)
    elif used_candidates:
        # Duplicate IDs can exist on the page. A stale hidden node is commonly 0,
        # so prefer the largest live-looking value rather than querySelector's first.
        used = max(used_candidates)
    else:
        raise BrowserAutomationError(
            "Не удалось прочитать текущее число полётов из Nemexia. Автофарм остановлен."
        )

    game_max = 0
    if text_max is not None and int(text_max) > 0:
        game_max = int(text_max)
    else:
        positive_max = [value for value in max_candidates if value > 0]
        if positive_max:
            game_max = max(positive_max)

    try:
        configured_max = int(getattr(self, "_configured_fleet_max", 0) or 0)
    except Exception:
        configured_max = 0

    maximum = game_max if game_max > 0 else configured_max

    if used < 0:
        raise BrowserAutomationError(f"Некорректное число текущих полётов: {used}.")
    if maximum <= 0:
        raise BrowserAutomationError(
            "Не удалось определить максимум флота ни из игры, ни из настройки «Макс. слотов»."
        )

    return {
        "used": used,
        "max": maximum,
        "free": max(0, maximum - used),
        "game_max": game_max,
        "configured_max": configured_max,
    }


def install_fleet_capacity_settings_fallback(browser_class: type[Any], app_class: type[Any]) -> None:
    """Use app `Макс. слотов` as fallback while keeping live game usage authoritative.

    Install this after fleet-capacity presentation so both manual sync and the
    auto-farm sender receive the current configured limit before reading capacity.
    """
    if app_class in _INSTALLED_CLASSES:
        return

    browser_class.read_fleet_capacity = _read_fleet_capacity_with_settings_fallback

    original_farm_send_wave = app_class._farm_send_wave
    original_sync_flights = app_class.sync_flights

    def set_configured_max(self: Any) -> int:
        configured = max(1, self._safe_int(self.max_slots_var, 15))
        self.worker._configured_fleet_max = configured
        return configured

    def farm_send_wave(self: Any) -> None:
        set_configured_max(self)
        return original_farm_send_wave(self)

    def sync_flights(self: Any, silent: bool = False) -> None:
        set_configured_max(self)
        return original_sync_flights(self, silent=silent)

    app_class._farm_send_wave = farm_send_wave
    app_class.sync_flights = sync_flights
    _INSTALLED_CLASSES.add(app_class)
