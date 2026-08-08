from __future__ import annotations

from datetime import datetime
from typing import Any

from v2.application.debris_source import BrowserDebrisSnapshot, BrowserDebrisStatus
from v2.domain.debris import debris_observation, parse_debris_square_info
from v2.infrastructure.cdp_asteroid_reader import ReadOnlyAsteroidCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError


class DebrisReadError(CdpReadError):
    """Raised when current-system debris evidence cannot be read safely."""


def snapshot_from_raw(
    raw: dict[str, Any],
    *,
    endpoint: str | None = None,
    page_url: str | None = None,
) -> BrowserDebrisSnapshot:
    """Map one parent asteroid-reader raw snapshot without hiding partial evidence."""

    server_time = raw.get("server_time")
    if not isinstance(server_time, (list, tuple)) or len(server_time) != 6:
        raise DebrisReadError("Не удалось доказать текущее серверное время на galaxy.php")
    try:
        observed_server_at = datetime(*(int(value) for value in server_time))
    except (TypeError, ValueError) as exc:
        raise DebrisReadError("Некорректное серверное время на galaxy.php") from exc

    raw_asteroids = tuple(raw.get("asteroids") or ())
    observations = []
    readable = 0
    unreadable_coords: list[str] = []
    seen: set[str] = set()
    for item in raw_asteroids:
        try:
            galaxy = int(item["g"])
            system = int(item["s"])
            position = int(item["p"])
            tooltip = str(item["tooltip"] or "")
        except (KeyError, TypeError, ValueError):
            unreadable_coords.append("unknown")
            continue
        coord = f"{galaxy}:{system}:{position}"
        if coord in seen:
            continue
        seen.add(coord)
        try:
            evidence = parse_debris_square_info(
                tooltip,
                galaxy=galaxy,
                system=system,
                position=position,
                observed_server_at=observed_server_at,
            )
        except ValueError:
            unreadable_coords.append(coord)
            continue
        readable += 1
        fact = debris_observation(evidence)
        if fact is not None:
            observations.append(fact)

    visible = len(seen) + unreadable_coords.count("unknown")
    detail = f"Attach-only debris read · {page_url or raw.get('page_url') or ''}".rstrip(" ·")
    if unreadable_coords:
        detail = (
            f"Partial current-system debris evidence: unreadable squareInfo for "
            f"{', '.join(unreadable_coords[:5])}"
        )
    return BrowserDebrisSnapshot(
        BrowserDebrisStatus(
            True,
            endpoint=endpoint,
            page_url=page_url or str(raw.get("page_url") or ""),
            detail=detail,
        ),
        visible_asteroids=visible,
        readable_square_info=readable,
        observations=tuple(observations),
    )


class ReadOnlyDebrisCdpBackend(ReadOnlyAsteroidCdpBackend):
    """Read debris only from the already-open/current ``galaxy.php`` system.

    Browser acquisition, DOM discovery and the read-only ``squareInfo`` POST are
    inherited from the V2 asteroid reader. That parent boundary never creates a
    page, navigates, switches systems/planets, calls ``refreshGalaxy`` or clicks.
    """

    def read_debris(self) -> BrowserDebrisSnapshot:
        try:
            raw = self._submit(self._read_current_galaxy())
        except CdpReadError as exc:
            return BrowserDebrisSnapshot(
                BrowserDebrisStatus(False, endpoint=self.endpoint, detail=str(exc))
            )

        page_url = str(raw.get("page_url") or "")
        if bool(raw.get("captcha_present")):
            return BrowserDebrisSnapshot(
                BrowserDebrisStatus(
                    False,
                    captcha_present=True,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="CAPTCHA обнаружена — debris read остановлен",
                )
            )
        if not bool(raw.get("ready")):
            return BrowserDebrisSnapshot(
                BrowserDebrisStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail="Открой нужную galaxy.php систему и дождись #galaxyHolder/currentTime",
                )
            )
        try:
            return snapshot_from_raw(raw, endpoint=self.endpoint, page_url=page_url)
        except DebrisReadError as exc:
            return BrowserDebrisSnapshot(
                BrowserDebrisStatus(
                    False,
                    endpoint=self.endpoint,
                    page_url=page_url,
                    detail=str(exc),
                )
            )
