from __future__ import annotations

from datetime import datetime
from typing import Any

from v2.application.asteroid_source import BrowserAsteroidSnapshot, BrowserAsteroidStatus
from v2.domain.asteroids import AsteroidObservationFact, parse_asteroid_tooltip
from v2.infrastructure.cdp_read_backend import CdpReadError, ReadOnlyCdpBackend


class AsteroidReadError(CdpReadError):
    """Raised when the current rendered galaxy evidence cannot be read safely."""


def observations_from_raw(raw: dict[str, Any]) -> tuple[AsteroidObservationFact, ...]:
    """Map one already-rendered galaxy snapshot into immutable observation facts."""

    server_time = raw.get("server_time")
    if not isinstance(server_time, (list, tuple)) or len(server_time) != 6:
        raise AsteroidReadError("Не удалось доказать текущее серверное время на galaxy.php")
    try:
        observed_server_at = datetime(*(int(value) for value in server_time))
    except (TypeError, ValueError) as exc:
        raise AsteroidReadError("Некорректное серверное время на galaxy.php") from exc

    output: list[AsteroidObservationFact] = []
    seen: set[str] = set()
    for item in raw.get("asteroids") or ():
        try:
            galaxy = int(item["g"])
            system = int(item["s"])
            position = int(item["p"])
            tooltip = str(item["tooltip"] or "")
        except (KeyError, TypeError, ValueError) as exc:
            raise AsteroidReadError("Некорректные координаты астероида в текущей системе") from exc
        coord = f"{galaxy}:{system}:{position}"
        if coord in seen:
            continue
        seen.add(coord)
        try:
            output.append(
                parse_asteroid_tooltip(
                    tooltip,
                    galaxy=galaxy,
                    system=system,
                    position=position,
                    observed_server_at=observed_server_at,
                )
            )
        except ValueError as exc:
            raise AsteroidReadError(f"Не удалось доказать movement-факты астероида {coord}: {exc}") from exc
    return tuple(output)


class ReadOnlyAsteroidCdpBackend(ReadOnlyCdpBackend):
    """Read asteroids from an already-open/current ``galaxy.php`` page only.

    The adapter never creates a page, navigates, switches planets/systems, calls
    ``refreshGalaxy`` or clicks game controls. For each asteroid already visible
    in ``#galaxyHolder`` it may issue the proven read-only ``squareInfo`` POST to
    ``ajax_info.php`` to obtain movement facts without changing the rendered page.
    """

    async def _existing_galaxy_page(self):
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        page = next(
            (
                item
                for item in pages
                if self.game_host in item.url and "galaxy.php" in item.url
            ),
            None,
        )
        if page is None:
            raise AsteroidReadError("Открой нужную galaxy.php систему в подключённом браузере")
        return page

    async def _read_current_galaxy(self) -> dict[str, Any]:
        page = await self._existing_galaxy_page()
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
                    const holder=document.querySelector('#galaxyHolder');
                    const d=(window.currentTime instanceof Date && !Number.isNaN(window.currentTime.getTime()))
                        ? window.currentTime : null;
                    const url=new URL(location.href);
                    const currentG=Number(document.querySelector('#c1')?.value || url.searchParams.get('galaxy') || 0);
                    const currentS=Number(document.querySelector('#c2')?.value || url.searchParams.get('solar') || 0);
                    const coords=[];
                    if(holder) {
                        holder.querySelectorAll('a').forEach(a => {
                            const asteroid=Array.from(a.querySelectorAll('img')).some(img =>
                                (img.getAttribute('src')||'').toLowerCase().includes('asteroid')
                            );
                            if(!asteroid) return;
                            let g=0,s=0,p=0;
                            try {
                                const href=new URL(a.getAttribute('href')||'', location.href);
                                g=Number(href.searchParams.get('c1')||0);
                                s=Number(href.searchParams.get('c2')||0);
                                p=Number(href.searchParams.get('c3')||0);
                            } catch (_) {}
                            if(!(g&&s&&p)) {
                                const m=(a.getAttribute('onmouseover')||'').match(/squareInfo\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/);
                                if(m) { g=Number(m[1]); s=Number(m[2]); p=Number(m[3]); }
                            }
                            if(g&&s&&p) coords.push({g,s,p});
                        });
                    }
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        ready:!!holder && currentG>0 && currentS>0 && !!d,
                        current_g:currentG,
                        current_s:currentS,
                        server_time:d ? [d.getFullYear(),d.getMonth()+1,d.getDate(),d.getHours(),d.getMinutes(),d.getSeconds()] : null,
                        coords
                    };
                }"""
            )
        except Exception as exc:
            raise AsteroidReadError("Не удалось прочитать текущий DOM galaxy.php") from exc

        if bool(raw.get("captcha_present")) or not bool(raw.get("ready")):
            return dict(raw)

        current_g = int(raw.get("current_g") or 0)
        current_s = int(raw.get("current_s") or 0)
        unique: list[dict[str, int]] = []
        seen: set[tuple[int, int, int]] = set()
        for item in raw.get("coords") or ():
            coord = (int(item.get("g") or 0), int(item.get("s") or 0), int(item.get("p") or 0))
            if coord in seen or coord[0] != current_g or coord[1] != current_s or coord[2] <= 0:
                continue
            seen.add(coord)
            unique.append({"g": coord[0], "s": coord[1], "p": coord[2]})

        asteroids: list[dict[str, Any]] = []
        for coord in unique:
            try:
                response = await page.evaluate(
                    r"""async coord => {
                        const body=new URLSearchParams({
                            type:'squareInfo', c1:String(coord.g), c2:String(coord.s), c3:String(coord.p)
                        }).toString();
                        const result=await fetch('ajax_info.php', {
                            method:'POST',
                            credentials:'same-origin',
                            headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                            body
                        });
                        return {ok:result.ok, status:result.status, text:await result.text()};
                    }""",
                    coord,
                )
            except Exception as exc:
                raise AsteroidReadError(
                    f"Не удалось прочитать squareInfo {coord['g']}:{coord['s']}:{coord['p']}"
                ) from exc
            text = str(response.get("text") or "")
            lower = text.casefold()
            if any(token in lower for token in (
                "are you human",
                "защита от автоматических действий",
                "humans only",
                "я не робот",
                "recaptcha",
            )):
                raw["captcha_present"] = True
                return dict(raw)
            if not bool(response.get("ok")):
                raise AsteroidReadError(
                    f"squareInfo {coord['g']}:{coord['s']}:{coord['p']} вернул HTTP {response.get('status')}"
                )
            asteroids.append({**coord, "tooltip": text})

        return {**dict(raw), "asteroids": asteroids}

    def read_asteroids(self) -> BrowserAsteroidSnapshot:
        try:
            raw = self._submit(self._read_current_galaxy())
        except CdpReadError as exc:
            return BrowserAsteroidSnapshot(
                BrowserAsteroidStatus(False, endpoint=self.endpoint, detail=str(exc))
            )

        page_url = str(raw.get("page_url") or "")
        if bool(raw.get("captcha_present")):
            return BrowserAsteroidSnapshot(
                BrowserAsteroidStatus(
                    False,
                    captcha_present=True,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="CAPTCHA обнаружена — asteroid read остановлен",
                )
            )
        if not bool(raw.get("ready")):
            return BrowserAsteroidSnapshot(
                BrowserAsteroidStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="Открой нужную galaxy.php систему и дождись #galaxyHolder/currentTime",
                )
            )
        try:
            observations = observations_from_raw(raw)
        except AsteroidReadError as exc:
            return BrowserAsteroidSnapshot(
                BrowserAsteroidStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail=str(exc),
                )
            )
        return BrowserAsteroidSnapshot(
            BrowserAsteroidStatus(
                True,
                endpoint=self.endpoint,
                page_url=page_url,
                detail=f"Attach-only asteroid read · {page_url}",
            ),
            observations,
        )
