from __future__ import annotations

from v2.application.automatic_recon import (
    AutomaticReconMutationError,
    ProcessableSpyFleet,
)
from v2.domain.recon import SpyReportFact
from v2.infrastructure.cdp_navigation_backend import V2NavigationCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError, extract_coord, parse_hms
from v2.infrastructure.spy_report_parser import parse_rendered_spy_reports


class V2AutomaticReconCdpBackend(V2NavigationCdpBackend):
    """AUTO-07 browser boundary over the single page owned by NavigationCoordinator."""

    async def _captcha_present(self, page) -> bool:
        return bool(
            await page.evaluate(
                r"""() => {
                    const text=(document.body?.innerText||'').replace(/\s+/g,' ').toLowerCase();
                    const recaptcha=!!document.querySelector(
                        'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
                    );
                    const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined'
                        && !!window.BOTCHECK_PAGE_LOCK;
                    return recaptcha || botLock || [
                        'are you human', 'защита от автоматических действий',
                        'humans only', 'я не робот'
                    ].some(value => text.includes(value));
                }"""
            )
        )

    async def _validated_page(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
        page_kind: str,
    ):
        page = await self._validate_expected_context(
            expected_planet_id=expected_planet_id,
            expected_coord=expected_coord,
            expected_account_fingerprint=expected_account_fingerprint,
        )
        state = await self._read_page_state(page)
        if state.page_kind != page_kind:
            raise CdpReadError(
                f"Automatic recon expected {page_kind} page, got {state.page_kind}"
            )
        if page_kind == "fleets" and not state.fleets_ready:
            raise CdpReadError("fleets.php is not ready for automatic recon")
        if page_kind == "options" and not state.messages_ready:
            raise CdpReadError("System messages are not ready for automatic recon")
        if await self._captcha_present(page):
            raise AutomaticReconMutationError(
                f"CAPTCHA detected on {page_kind}; automatic recon stopped",
                remote_attempted=False,
                captcha_present=True,
            )
        return page

    async def _discover_spy_fleets(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[ProcessableSpyFleet, ...]:
        page = await self._validated_page(
            expected_planet_id=expected_planet_id,
            expected_coord=expected_coord,
            expected_account_fingerprint=expected_account_fingerprint,
            page_kind="fleets",
        )
        try:
            rows = await page.evaluate(
                r"""() => Array.from(document.querySelectorAll('a[id^="spy1Link-"]')).map(link => {
                    const fleetId=(link.id||'').slice('spy1Link-'.length);
                    const tr=link.closest('tr');
                    if (!/^\d+$/.test(fleetId) || !tr) return null;
                    const cells=Array.from(tr.children).filter(el => el.tagName === 'TD');
                    const timer=document.getElementById(`spy1Time-${fleetId}`);
                    return {
                        fleet_id:fleetId,
                        source:cells[0]?.textContent?.trim()||'',
                        target:cells[1]?.textContent?.trim()||'',
                        onclick:link.getAttribute('onclick')||'',
                        timer:timer?.textContent?.trim()||''
                    };
                }).filter(Boolean)"""
            )
        except Exception as exc:
            raise CdpReadError("Failed to read exact spy fleet DOM") from exc

        result: list[ProcessableSpyFleet] = []
        for raw in rows:
            fleet_id = str(raw.get("fleet_id") or "").strip()
            onclick = str(raw.get("onclick") or "").replace(" ", "").strip()
            if onclick not in {f"processSpy({fleet_id})", f"processSpy({fleet_id});"}:
                continue
            source = extract_coord(str(raw.get("source") or ""))
            target = extract_coord(str(raw.get("target") or ""))
            if source.count(":") != 2 or target.count(":") != 2:
                continue
            result.append(
                ProcessableSpyFleet(
                    fleet_id=fleet_id,
                    source=source,
                    target=target,
                    remaining_seconds=parse_hms(str(raw.get("timer") or "")),
                )
            )
        return tuple(result)

    def discover_spy_fleets(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[ProcessableSpyFleet, ...]:
        return self._submit(
            self._discover_spy_fleets(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )

    async def _read_spy_reports(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[SpyReportFact, ...]:
        page = await self._validated_page(
            expected_planet_id=expected_planet_id,
            expected_coord=expected_coord,
            expected_account_fingerprint=expected_account_fingerprint,
            page_kind="options",
        )
        try:
            html = await page.evaluate(
                r"""() => {
                    const root=document.querySelector('#TabAdministrativeBox')
                        || document.querySelector('#TabAdministrative');
                    return root ? root.outerHTML : '';
                }"""
            )
        except Exception as exc:
            raise CdpReadError("Failed to read rendered System messages") from exc
        if not html:
            raise CdpReadError("Rendered System messages DOM is empty")
        return parse_rendered_spy_reports(str(html))

    def read_spy_reports(
        self,
        *,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> tuple[SpyReportFact, ...]:
        return self._submit(
            self._read_spy_reports(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )

    async def _process_spy_once(
        self,
        *,
        fleet_id: str,
        expected_source: str,
        expected_target: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> None:
        try:
            page = await self._validated_page(
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
                page_kind="fleets",
            )
            raw = await page.evaluate(
                r"""fleetId => {
                    const link=document.getElementById(`spy1Link-${fleetId}`);
                    const timer=document.getElementById(`spy1Time-${fleetId}`);
                    const tr=link?.closest('tr');
                    if (!link || !timer || !tr) return null;
                    const cells=Array.from(tr.children).filter(el => el.tagName === 'TD');
                    return {
                        onclick:link.getAttribute('onclick')||'',
                        source:cells[0]?.textContent?.trim()||'',
                        target:cells[1]?.textContent?.trim()||'',
                        timer:timer.textContent?.trim()||'',
                        processSpy:typeof window.processSpy === 'function'
                    };
                }""",
                str(fleet_id),
            )
            if not raw:
                raise CdpReadError(f"Spy fleet {fleet_id} disappeared before processSpy")
            onclick = str(raw.get("onclick") or "").replace(" ", "").strip()
            if onclick not in {f"processSpy({fleet_id})", f"processSpy({fleet_id});"}:
                raise CdpReadError("Exact processSpy DOM action changed before mutation")
            source = extract_coord(str(raw.get("source") or ""))
            target = extract_coord(str(raw.get("target") or ""))
            if source != str(expected_source) or target != str(expected_target):
                raise CdpReadError("Spy fleet route changed before mutation")
            remaining = parse_hms(str(raw.get("timer") or ""))
            if remaining is None or remaining > 0:
                raise CdpReadError("Spy fleet timer is not proven ready before mutation")
            if not bool(raw.get("processSpy")):
                raise CdpReadError("window.processSpy is unavailable")
        except AutomaticReconMutationError:
            raise
        except Exception as exc:
            raise AutomaticReconMutationError(
                f"Automatic recon preflight failed before processSpy: {exc}",
                remote_attempted=False,
            ) from exc

        try:
            await page.evaluate(
                """fleetId => {
                    window.processSpy(Number(fleetId));
                }""",
                str(fleet_id),
            )
        except Exception as exc:
            raise AutomaticReconMutationError(
                "processSpy was attempted but its remote effect is ambiguous",
                remote_attempted=True,
            ) from exc

    def process_spy_once(
        self,
        *,
        fleet_id: str,
        expected_source: str,
        expected_target: str,
        expected_planet_id: str,
        expected_coord: str,
        expected_account_fingerprint: str,
    ) -> None:
        self._submit(
            self._process_spy_once(
                fleet_id=fleet_id,
                expected_source=expected_source,
                expected_target=expected_target,
                expected_planet_id=expected_planet_id,
                expected_coord=expected_coord,
                expected_account_fingerprint=expected_account_fingerprint,
            )
        )
