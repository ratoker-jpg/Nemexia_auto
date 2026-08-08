from __future__ import annotations

from v2.infrastructure.cdp_read_backend import CdpReadError, ReadOnlyCdpBackend, extract_coord


class ReadOnlyAccountCdpBackend(ReadOnlyCdpBackend):
    """Extend the attach-only fleet reader with account-coordinate facts.

    This reader only inspects the already-rendered `#planetsListHolder` DOM. It
    deliberately does not follow links, switch planets, create tabs or navigate.
    """

    async def _read_owned_planets(self) -> tuple[str, ...]:
        page = await self._existing_fleets_page()
        try:
            values = await page.evaluate(
                r"""() => Array.from(document.querySelectorAll('#planetsListHolder a'))
                    .map(a => (a.textContent || '').trim())"""
            )
        except Exception as exc:
            raise CdpReadError("Не удалось прочитать список собственных планет") from exc
        coords = {extract_coord(str(value)) for value in values}
        return tuple(sorted(coord for coord in coords if coord.count(":") == 2))

    def owned_planets(self) -> tuple[str, ...]:
        try:
            snapshot = self._snapshot()
        except CdpReadError:
            return ()
        if snapshot.captcha_present:
            return ()
        try:
            return tuple(self._submit(self._read_owned_planets()))
        except CdpReadError:
            return ()
