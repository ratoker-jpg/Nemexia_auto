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

_BROWSER_LOSS_TOKENS = (
    "execution context was destroyed",
    "target page, context or browser has been closed",
    "target page has been closed",
    "page has been closed",
    "browser has been closed",
)


def _is_bot_check_url(url: str) -> bool:
    """Recognize the proven game protection route without requiring page DOM."""

    return (urlsplit(str(url)).path or "").casefold().endswith("/bot_check.php")


def _exception_chain_text(exc: BaseException) -> str:
    """Keep wrapped Playwright/CDP evidence instead of only the outer generic error."""

    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(parts) < 8:
        seen.add(id(current))
        text = str(current) or current.__class__.__name__
        if text not in parts:
            parts.append(text)
        current = current.__cause__ or current.__context__
    return " | caused by: ".join(parts)


def _contains_browser_loss(detail: str) -> bool:
    folded = str(detail).casefold()
    return any(token in folded for token in _BROWSER_LOSS_TOKENS)


def _evaluation_failure_detail(exc: Exception) -> str:
    """Retain raw page error while tagging proven browser/context-loss shapes."""

    detail = _exception_chain_text(exc)
    if _contains_browser_loss(detail):
        return f"Browser/session loss during Rest Mode observation: {detail}"
    return f"Rest Mode observation evaluation failed: {detail}"


def _identity_failure(exc: Exception, *, phase: str) -> tuple[str, str]:
    """Classify wrapped identity-read failures without discarding their root cause."""

    detail = _exception_chain_text(exc)
    folded = detail.casefold()
    if any(
        token in folded
        for token in (
            "captcha",
            "humans only",
            "защита от автоматических действий",
            "я не робот",
        )
    ):
        return "captcha", f"CAPTCHA = STOP during Rest Mode identity read ({phase}): {detail}"
    if _contains_browser_loss(detail):
        return "browser", f"Browser/session loss during Rest Mode identity read ({phase}): {detail}"
    return "identity", f"Rest Mode identity unavailable during {phase}: {detail}"


class OwnedRestModeReadMixin:
    """Read activity/CAPTCHA facts only from NavigationCoordinator's bound page."""

    async def _identity_or_raise(self, *, phase: str):
        try:
            return await self._read_browser_identity()
        except CdpReadError as exc:
            kind, detail = _identity_failure(exc, phase=phase)
            if kind in {"captcha", "browser"}:
                raise RestModeReadError(detail) from exc
            raise RestModeIdentityError(detail) from exc

    async def _read_rest_mode_observation(
        self,
        *,
        expected_server_host: str,
        expected_account_fingerprint: str,
        expected_planet_id: str,
        expected_coord: str,
    ) -> RestModeObservation:
        page = await self._existing_bound_page()
        page_url = str(page.url)

        # The approved AUTO-12 contract recognizes bot_check.php as affirmative
        # CAPTCHA/protection evidence. Check it before identity or fleets DOM reads:
        # the protection page may intentionally have no planet selector to prove.
        if _is_bot_check_url(page_url):
            return RestModeObservation(
                observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                activity_minutes=0,
                captcha_required=True,
                detail="CAPTCHA / bot-check detected from coordinator-owned bot_check.php URL",
            )

        identity = await self._identity_or_raise(phase="pre-read")
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

        path = (urlsplit(page_url).path or "").casefold()
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

                    // Saved real fleets.php proves this exact visible surface:
                    // #serverTimeDisplay onmouseover="Tip(getServerTimeTooltip());".
                    // Do not scan arbitrary tooltip/title attributes: only the
                    // rendered game-owned server-time anchor can authorize a timer.
                    const timer=document.querySelector('#serverTimeDisplay');
                    const style=timer ? window.getComputedStyle(timer) : null;
                    const rect=timer ? timer.getBoundingClientRect() : null;
                    const timerVisible=!!timer && !!style && !!rect
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || '1') > 0
                        && rect.width > 0 && rect.height > 0;
                    const timerHook=(timer?.getAttribute('onmouseover')||'').includes('getServerTimeTooltip');
                    let activityTooltip='';
                    if(timerVisible && timerHook && typeof window.getServerTimeTooltip === 'function'){
                        try {
                            activityTooltip=String(window.getServerTimeTooltip()||'')
                                .replace(/\s+/g,' ').trim();
                        } catch (_) {
                            activityTooltip='';
                        }
                    }
                    return {
                        page_url:location.href,
                        captcha_present:captcha,
                        timer_visible:timerVisible,
                        timer_hook:timerHook,
                        activity_tooltip:activityTooltip
                    };
                }"""
            )
        except Exception as exc:
            # Preserve the underlying Playwright/CDP diagnostic and translate only
            # known tab/context-loss shapes so the application persists BLOCKED_BROWSER.
            raise RestModeReadError(_evaluation_failure_detail(exc)) from exc

        if bool(raw.get("captcha_present")):
            return RestModeObservation(
                observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                activity_minutes=0,
                captcha_required=True,
                detail="CAPTCHA / bot-check detected on coordinator-owned page",
            )

        if not bool(raw.get("timer_visible")) or not bool(raw.get("timer_hook")):
            raise RestModeReadError(
                "Activity timer surface #serverTimeDisplay is missing, hidden, or no longer bound to "
                "getServerTimeTooltip(); fail-closed"
            )
        tooltip = str(raw.get("activity_tooltip") or "")
        match = _ACTIVITY_RE.search(tooltip)
        if match is None:
            raise RestModeReadError(
                "Activity timer is not proven by visible #serverTimeDisplay / getServerTimeTooltip() "
                "human-readable 'Автоматический режим проверки через N мин.' evidence; "
                "raw BOT_CHECK units are intentionally ignored"
            )
        activity_minutes = int(match.group(1))
        evidence = match.group(0)

        final_identity = await self._identity_or_raise(phase="post-read")
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
