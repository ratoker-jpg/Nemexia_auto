from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Coroutine

from playwright.async_api import Browser, Page, Playwright, async_playwright

from v2.application.browser_read_service import (
    BrowserFleetCapacity,
    BrowserFlightRecord,
    BrowserReadStatus,
)


class CdpReadError(RuntimeError):
    """Raised when V2 cannot safely read the already-open Nemexia fleet page."""


@dataclass(frozen=True)
class _DomFlightRow:
    fleet_id: str | None
    source: str
    target: str
    mission: str
    arrival: str
    returning: str


@dataclass(frozen=True)
class _DomSnapshot:
    page_url: str
    captcha_present: bool
    used_text: str
    maximum_text: str
    rows: tuple[_DomFlightRow, ...]


def parse_hms(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", value.strip())
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def extract_coord(value: str | None) -> str:
    match = re.search(r"(\d+)\s*:\s*(\d+)\s*:\s*(\d+)", value or "")
    return ":".join(match.groups()) if match else str(value or "").replace(" ", "")


def parse_counter(value: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    return int(digits) if digits else None


def map_dom_flight(row: _DomFlightRow, *, now: datetime | None = None) -> BrowserFlightRecord | None:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    arrival_seconds = parse_hms(row.arrival)
    return_seconds = parse_hms(row.returning)
    if arrival_seconds is None and return_seconds is None:
        return None

    arrival_at = current + timedelta(seconds=arrival_seconds) if arrival_seconds is not None else None
    return_at = current + timedelta(seconds=return_seconds) if return_seconds is not None else None
    departure_at = arrival_at + (arrival_at - return_at) if arrival_at and return_at else None
    return BrowserFlightRecord(
        source=extract_coord(row.source),
        target=extract_coord(row.target),
        mission=row.mission.strip(),
        departure_at=departure_at.isoformat() if departure_at else None,
        arrival_at=arrival_at.isoformat() if arrival_at else None,
        return_at=return_at.isoformat() if return_at else None,
        fleet_id=row.fleet_id,
    )


class ReadOnlyCdpBackend:
    """Attach to an existing Chromium CDP session and read the current fleet DOM.

    The adapter is deliberately attach-only: it never opens a tab, navigates,
    refreshes the fleet widget, focuses a page, clicks controls or executes game
    actions. If an already-open ``fleets.php`` page is not present, the source is
    reported as unavailable and the user must open that page manually.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        game_host: str = "game.ares.nemexia.com",
        timeout_seconds: float = 3.0,
        cache_seconds: float = 0.75,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.game_host = game_host
        self.timeout_seconds = max(0.5, float(timeout_seconds))
        self.cache_seconds = max(0.0, float(cache_seconds))
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="nemexia-v2-cdp-read")
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._closed = False
        self._cache: _DomSnapshot | None = None
        self._cache_at = 0.0
        self._cache_lock = threading.Lock()
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def _submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        if self._closed or self._loop is None:
            raise CdpReadError("CDP read backend is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=self.timeout_seconds + 1.0)
        except Exception as exc:
            future.cancel()
            raise CdpReadError(str(exc) or exc.__class__.__name__) from exc

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.endpoint,
                timeout=int(self.timeout_seconds * 1000),
            )
        except Exception as exc:
            self._browser = None
            raise CdpReadError(f"CDP недоступен: {self.endpoint}") from exc
        return self._browser

    async def _existing_fleets_page(self) -> Page:
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        page = next(
            (
                item
                for item in pages
                if self.game_host in item.url and "fleets.php" in item.url
            ),
            None,
        )
        if page is None:
            raise CdpReadError("Открой fleets.php в уже подключённом браузере")
        return page

    async def _read_dom(self) -> _DomSnapshot:
        page = await self._existing_fleets_page()
        try:
            raw = await page.evaluate(
                r"""() => {
                    const bodyText=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                    const lower=bodyText.toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    const phrases=[
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ];
                    const captcha=recaptcha || botLock || phrases.some(value => lower.includes(value));
                    const rows=Array.from(document.querySelectorAll('#fleetHandler tbody tr')).map(row => {
                        const cells=Array.from(row.children).filter(el => el.tagName==='TD');
                        const details=row.querySelector('.fleetType a');
                        const onclick=details?.getAttribute('onclick')||'';
                        const match=onclick.match(/fleetDetails\((\d+)\)/);
                        return {
                            fleet_id:match?match[1]:null,
                            source:cells[0]?.textContent?.trim()||'',
                            target:cells[1]?.textContent?.trim()||'',
                            arrival:row.querySelector('[id^="arrive1Time-"]')?.textContent?.trim()||'',
                            returning:row.querySelector('[id^="arrive2Time-"]')?.textContent?.trim()||'',
                            mission:details?.textContent?.trim()||cells[4]?.textContent?.trim()||''
                        };
                    });
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        used_text:document.querySelector('#FleetsCount')?.textContent?.trim()||'',
                        maximum_text:document.querySelector('#MaxFleets')?.textContent?.trim()||'',
                        rows
                    };
                }"""
            )
        except Exception as exc:
            self._browser = None
            raise CdpReadError("Не удалось прочитать DOM fleets.php") from exc
        rows = tuple(
            _DomFlightRow(
                fleet_id=str(item.get("fleet_id")) if item.get("fleet_id") else None,
                source=str(item.get("source") or ""),
                target=str(item.get("target") or ""),
                mission=str(item.get("mission") or ""),
                arrival=str(item.get("arrival") or ""),
                returning=str(item.get("returning") or ""),
            )
            for item in (raw.get("rows") or [])
        )
        return _DomSnapshot(
            page_url=str(raw.get("page_url") or page.url),
            captcha_present=bool(raw.get("captcha_present")),
            used_text=str(raw.get("used_text") or ""),
            maximum_text=str(raw.get("maximum_text") or ""),
            rows=rows,
        )

    def _snapshot(self) -> _DomSnapshot:
        now = time.monotonic()
        with self._cache_lock:
            if self._cache is not None and now - self._cache_at <= self.cache_seconds:
                return self._cache
        snapshot = self._submit(self._read_dom())
        with self._cache_lock:
            self._cache = snapshot
            self._cache_at = time.monotonic()
        return snapshot

    def invalidate(self) -> None:
        with self._cache_lock:
            self._cache = None
            self._cache_at = 0.0

    def status(self) -> BrowserReadStatus:
        try:
            snapshot = self._snapshot()
        except CdpReadError as exc:
            return BrowserReadStatus(False, endpoint=self.endpoint, detail=str(exc))
        if snapshot.captcha_present:
            return BrowserReadStatus(
                True,
                captcha_present=True,
                endpoint=self.endpoint,
                detail="CAPTCHA обнаружена — live-read остановлен до ручного подтверждения",
            )
        return BrowserReadStatus(
            True,
            endpoint=self.endpoint,
            detail=f"CDP read-only · {snapshot.page_url}",
        )

    def flights(self) -> tuple[BrowserFlightRecord, ...]:
        try:
            snapshot = self._snapshot()
        except CdpReadError:
            return ()
        if snapshot.captcha_present:
            return ()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        records = [map_dom_flight(row, now=now) for row in snapshot.rows]
        return tuple(record for record in records if record is not None)

    def capacity(self) -> BrowserFleetCapacity | None:
        try:
            snapshot = self._snapshot()
        except CdpReadError:
            return None
        if snapshot.captcha_present:
            return None
        used = parse_counter(snapshot.used_text)
        maximum = parse_counter(snapshot.maximum_text)
        if used is None or maximum is None or maximum <= 0 or used > maximum:
            return None
        return BrowserFleetCapacity(used=used, maximum=maximum)

    async def _stop_playwright(self) -> None:
        # Never call Browser.close() here: V2 attached to a browser owned by the user.
        self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._submit(self._stop_playwright())
        except Exception:
            pass
        self._closed = True
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
