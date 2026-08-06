from __future__ import annotations

from typing import Any

from browser import BrowserAutomationError, BrowserWorker
from config import GAME_HOST


_ORIGINAL_CONNECT = BrowserWorker.connect
_ORIGINAL_SELECT_PAGE = BrowserWorker._select_nemexia_page
_INSTALLED = False


def _all_open_pages(worker: BrowserWorker) -> list[Any]:
    browser = getattr(worker, "_browser", None)
    if browser is None:
        return []
    return [
        page
        for context in browser.contexts
        for page in context.pages
        if not page.is_closed()
    ]


def _bound_page_is_valid(worker: BrowserWorker, page: Any) -> bool:
    if page is None:
        return False
    try:
        return (
            not page.is_closed()
            and GAME_HOST in str(page.url)
            and page in _all_open_pages(worker)
        )
    except Exception:
        return False


async def _choose_active_game_page(worker: BrowserWorker) -> Any:
    game_pages = [page for page in _all_open_pages(worker) if GAME_HOST in str(page.url)]
    if not game_pages:
        raise BrowserAutomationError("Открытая вкладка Nemexia не найдена")

    focused: list[Any] = []
    visible: list[Any] = []
    for page in game_pages:
        try:
            state = await page.evaluate(
                "() => ({ focused: document.hasFocus(), visible: document.visibilityState === 'visible' })"
            )
        except Exception:
            state = {}
        if state.get("focused"):
            focused.append(page)
        if state.get("visible"):
            visible.append(page)

    if len(focused) == 1:
        return focused[0]
    if len(visible) == 1:
        return visible[0]
    if len(game_pages) == 1:
        return game_pages[0]

    raise BrowserAutomationError(
        "Открыто несколько активных вкладок Nemexia. Оставь нужную вкладку активной "
        "в одном окне браузера и нажми «Подключиться» ещё раз."
    )


async def _connect_and_bind(self: BrowserWorker, endpoint: str) -> dict[str, Any]:
    # Explicit Connect is the only operation allowed to replace a lost or changed binding.
    bound = getattr(self, "_bound_nemexia_page", None)
    if bound is not None and not _bound_page_is_valid(self, bound):
        self._bound_nemexia_page = None
    if getattr(self, "_endpoint", None) not in (None, endpoint):
        self._bound_nemexia_page = None

    await _ORIGINAL_CONNECT(self, endpoint)
    page = await _choose_active_game_page(self)
    self._bound_nemexia_page = page
    self._page = page
    return {
        "url": page.url,
        "pages": self._page_count(),
        "bound": True,
    }


async def _select_bound_page(self: BrowserWorker, create_if_missing: bool = False) -> Any:
    bound = getattr(self, "_bound_nemexia_page", None)
    if bound is not None:
        if not _bound_page_is_valid(self, bound):
            raise BrowserAutomationError(
                "Привязанная вкладка Nemexia закрыта или недоступна. "
                "Открой нужную вкладку и нажми «Подключиться» заново."
            )
        self._page = bound
        return bound

    # The original selector is used only while the initial CDP connection is being established.
    return await _ORIGINAL_SELECT_PAGE(self, create_if_missing=create_if_missing)


def install_bound_tab_fix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    BrowserWorker.connect = _connect_and_bind
    BrowserWorker._select_nemexia_page = _select_bound_page
    _INSTALLED = True
