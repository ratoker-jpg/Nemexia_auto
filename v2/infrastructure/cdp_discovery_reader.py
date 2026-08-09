from __future__ import annotations

from datetime import datetime
from typing import Any

from v2.application.discovery_scan import DiscoverySystemEvidence
from v2.infrastructure.cdp_asteroid_reader import AsteroidReadError, observations_from_raw
from v2.infrastructure.cdp_debris_reader import DebrisReadError, snapshot_from_raw


def _validated_visible_asteroid_coords(
    raw: dict[str, Any],
    *,
    expected_galaxy: int,
    expected_solar: int,
) -> list[dict[str, int]]:
    """Reject any visible asteroid candidate whose coordinate is not fully proven."""

    visible = int(raw.get("visible_asteroids") or 0)
    unparseable = int(raw.get("unparseable_asteroids") or 0)
    candidates = tuple(raw.get("coords") or ())
    if visible < 0 or unparseable < 0 or unparseable > visible:
        raise AsteroidReadError("Invalid visible asteroid evidence counters")
    if unparseable or len(candidates) + unparseable < visible:
        raise AsteroidReadError(
            "Visible asteroid candidate has missing or unparseable coordinates"
        )

    unique: list[dict[str, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for item in candidates:
        try:
            coord = (
                int(item.get("g") or 0),
                int(item.get("s") or 0),
                int(item.get("p") or 0),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise AsteroidReadError("Visible asteroid coordinate evidence is malformed") from exc
        if (
            coord[0] != int(expected_galaxy)
            or coord[1] != int(expected_solar)
            or coord[2] <= 0
        ):
            raise AsteroidReadError(
                "Visible asteroid coordinate does not match the requested discovery system"
            )
        if coord in seen:
            continue
        seen.add(coord)
        unique.append({"g": coord[0], "s": coord[1], "p": coord[2]})
    return unique


class OwnedDiscoveryReadMixin:
    """Read asteroid/debris evidence only from NavigationCoordinator's bound page."""

    async def _read_owned_discovery_raw(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
        expected_galaxy: int,
        expected_solar: int,
    ) -> dict[str, Any]:
        page = await self._validate_expected_context(
            expected_planet_id=expected_planet_id,
            expected_coord=expected_coord,
            expected_account_fingerprint=expected_account_fingerprint,
        )
        state = await self._read_page_state(page)
        if (
            state.page_kind != "galaxy"
            or not state.galaxy_ready
            or state.galaxy != int(expected_galaxy)
            or state.solar != int(expected_solar)
        ):
            raise AsteroidReadError(
                "Owned galaxy page does not match the requested discovery system"
            )
        captcha = getattr(self, "_captcha_present", None)
        if callable(captcha) and await captcha(page):
            raise AsteroidReadError("CAPTCHA detected before discovery evidence read")

        try:
            raw = await page.evaluate(
                r"""() => {
                    const holder=document.querySelector('#galaxyHolder');
                    const d=(window.currentTime instanceof Date && !Number.isNaN(window.currentTime.getTime()))
                        ? window.currentTime : null;
                    const g=Number(document.querySelector('#c1')?.value || 0);
                    const s=Number(document.querySelector('#c2')?.value || 0);
                    const coords=[];
                    let visibleAsteroids=0;
                    let unparseableAsteroids=0;
                    if(holder) {
                        holder.querySelectorAll('a').forEach(a => {
                            const asteroid=Array.from(a.querySelectorAll('img')).some(img =>
                                (img.getAttribute('src')||'').toLowerCase().includes('asteroid')
                            );
                            if(!asteroid) return;
                            visibleAsteroids += 1;
                            let c1=0,c2=0,c3=0;
                            try {
                                const href=new URL(a.getAttribute('href')||'', location.href);
                                c1=Number(href.searchParams.get('c1')||0);
                                c2=Number(href.searchParams.get('c2')||0);
                                c3=Number(href.searchParams.get('c3')||0);
                            } catch (_) {}
                            if(!(c1&&c2&&c3)) {
                                const m=(a.getAttribute('onmouseover')||'').match(
                                    /squareInfo\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/
                                );
                                if(m) { c1=Number(m[1]); c2=Number(m[2]); c3=Number(m[3]); }
                            }
                            if(c1&&c2&&c3) {
                                coords.push({g:c1,s:c2,p:c3});
                            } else {
                                unparseableAsteroids += 1;
                            }
                        });
                    }
                    return {
                        page_url:location.href,
                        ready:!!holder && !!d && g>0 && s>0,
                        current_g:g,
                        current_s:s,
                        server_time:d ? [
                            d.getFullYear(),d.getMonth()+1,d.getDate(),
                            d.getHours(),d.getMinutes(),d.getSeconds()
                        ] : null,
                        visible_asteroids:visibleAsteroids,
                        unparseable_asteroids:unparseableAsteroids,
                        coords
                    };
                }"""
            )
        except Exception as exc:
            raise AsteroidReadError("Failed to read owned galaxy discovery DOM") from exc

        if (
            not bool(raw.get("ready"))
            or int(raw.get("current_g") or 0) != int(expected_galaxy)
            or int(raw.get("current_s") or 0) != int(expected_solar)
        ):
            raise AsteroidReadError("Owned galaxy discovery DOM is not ready for requested system")

        unique = _validated_visible_asteroid_coords(
            raw,
            expected_galaxy=int(expected_galaxy),
            expected_solar=int(expected_solar),
        )

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
                    f"Failed to read squareInfo {coord['g']}:{coord['s']}:{coord['p']}"
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
                raise AsteroidReadError("CAPTCHA detected during discovery squareInfo read")
            if not bool(response.get("ok")):
                raise AsteroidReadError(
                    f"squareInfo {coord['g']}:{coord['s']}:{coord['p']} returned HTTP {response.get('status')}"
                )
            asteroids.append({**coord, "tooltip": text})

        if callable(captcha) and await captcha(page):
            raise AsteroidReadError("CAPTCHA detected after discovery evidence read")
        return {**dict(raw), "asteroids": asteroids}

    async def _read_discovery_system(self, **kwargs) -> DiscoverySystemEvidence:
        raw = await self._read_owned_discovery_raw(**kwargs)
        server_time = raw.get("server_time")
        if not isinstance(server_time, (list, tuple)) or len(server_time) != 6:
            raise AsteroidReadError("Discovery server time is not proven")
        try:
            observed_server_at = datetime(*(int(value) for value in server_time))
            asteroids = observations_from_raw(raw)
            debris_snapshot = snapshot_from_raw(raw, page_url=str(raw.get("page_url") or ""))
        except (TypeError, ValueError, AsteroidReadError, DebrisReadError) as exc:
            raise AsteroidReadError(f"Discovery evidence parse failed: {exc}") from exc
        return DiscoverySystemEvidence(
            galaxy=int(raw["current_g"]),
            solar=int(raw["current_s"]),
            observed_server_at=observed_server_at,
            visible_asteroids=debris_snapshot.visible_asteroids,
            readable_square_info=debris_snapshot.readable_square_info,
            asteroids=tuple(asteroids),
            debris=tuple(debris_snapshot.observations),
        )

    def read_discovery_system(self, **kwargs) -> DiscoverySystemEvidence:
        return self._submit(self._read_discovery_system(**kwargs))
