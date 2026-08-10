from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from v2.application.rest_mode import (
    RestModeIdentityError,
    RestModeObservation,
    RestModeReadError,
)
from v2.infrastructure.cdp_read_backend import CdpReadError


_ACTIVITY_RE = re.compile(
    r"Автоматический\s+режим\s+проверки\s+через\s+(\d+)\s*мин(?:\.|ут(?:ы|у)?)?",
    re.IGNORECASE,
)


class OwnedRestModeReadMixin:
    """Read activity/CAPTCHA facts only from NavigationCoordinator's bound page."""

    async def _read_rest_mode_observation(
        self,
        *,
        expected_server_host: str,
        expected_account_fingerprint: str,
        expected_planet_id: str,
        expected_coord: str,
    ) -> RestModeObservation:
        page = await self._existing_bound_page()
        identity = await self._read_browser_identity()
        current = identity.current_planet
        if identity.session.server_host != str(expected_server_host):
            raise RestModeIdentityError("Rest Mode server host changed before read")
        if identity.account.ownership_fingerprint != str(expected_account_fingerprint):
            raise RestModeIdentityError("Rest Mode account fingerprint changed before read")
        if (
            current is None
            or current.planet_id != str(expected_planet_id)
            or current.coord != str(expected_coord)
        ):
            raise RestModeIdentityError("Rest Mode PlanetIdentity changed before read")

        path = (urlsplit(str(page.url)).path or "").casefold()
        if not path.endswith("/fleets.php"):
            raise RestModeReadError("Rest Mode reader requires verified fleets.php")

        try:
            raw = await page.evaluate(
                r"""() => {
                    const bodyText=(document.body?.innerText||'').replace(/\s+/g,' ').trim();
                    const lower=bodyText.toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
                    const path=(location.pathname||'').toLowerCase();
                    const captcha=recaptcha || botLock || path.endsWith('/bot_check.php') || [
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ].some(value => lower.includes(value));
                    const rendered=[];
                    const push=value => {
                        const text=String(value||'').replace(/\s+/g,' ').trim();
                        if(text && !rendered.includes(text)) rendered.push(text);
                    };
                    push(bodyText);
                    for(const node of Array.from(document.querySelectorAll('[title],[aria-label],[data-original-title]'))){
                        push(node.getAttribute('title'));
                        push(node.getAttribute('aria-label'));
                        push(node.getAttribute('data-original-title'));
                    }
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        rendered_texts:rendered
                    };
                }"""
            )
        except Exception as exc:
            raise RestModeReadError("Не удалось прочитать Rest Mode observation") from exc

        if bool(raw.get("captcha_present")):
            return RestModeObservation(
                observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                activity_minutes=0,
                captcha_required=True,
                detail="CAPTCHA / bot-check detected on coordinator-owned page",
            )

        activity_minutes: int | None = None
        evidence = ""
        for text in raw.get("rendered_texts") or ():
            match = _ACTIVITY_RE.search(str(text))
            if match is None:
                continue
            activity_minutes = int(match.group(1))
            evidence = match.group(0)
            break
        if activity_minutes is None:
            raise RestModeReadError(
                "Activity timer is not proven by rendered 'Автоматический режим проверки через N мин.' evidence; "
                "raw BOT_CHECK units are intentionally ignored"
            )

        try:
            final_identity = await self._read_browser_identity()
        except CdpReadError as exc:
            detail = str(exc) or exc.__class__.__name__
            folded = detail.casefold()
            if "captcha" in folded or "защита от автоматических действий" in folded:
                raise RestModeReadError(f"CAPTCHA = STOP: {detail}") from exc
            raise RestModeReadError(detail) from exc
        final = final_identity.current_planet
        if (
            final_identity.session.server_host != str(expected_server_host)
            or final_identity.account.ownership_fingerprint != str(expected_account_fingerprint)
            or final is None
            or final.planet_id != str(expected_planet_id)
            or final.coord != str(expected_coord)
        ):
            raise RestModeIdentityError("Rest Mode identity changed during read")

        return RestModeObservation(
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            activity_minutes=activity_minutes,
            captcha_required=False,
            detail=evidence,
        )

    def read_rest_mode_observation(
        self,
        *,
        expected_server_host: str,
        expected_account_fingerprint: str,
        expected_planet_id: str,
        expected_coord: str,
    ) -> RestModeObservation:
        return self._submit(
            self._read_rest_mode_observation(
                expected_server_host=str(expected_server_host),
                expected_account_fingerprint=str(expected_account_fingerprint),
                expected_planet_id=str(expected_planet_id),
                expected_coord=str(expected_coord),
            )
        )
