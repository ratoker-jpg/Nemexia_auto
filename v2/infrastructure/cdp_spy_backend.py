from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone

from v2.application.spy_actions import (
    SpyActionError,
    SpyCaptchaBlocked,
    SpyRequestCommand,
    SpyRequestPreparation,
    SpyRequestResult,
)
from v2.domain.recon import SpyReportFact
from v2.infrastructure.cdp_account_reader import ReadOnlyAccountCdpBackend
from v2.infrastructure.cdp_read_backend import CdpReadError, extract_coord
from v2.infrastructure.spy_report_parser import parse_rendered_spy_reports


_PROCESS_ONCLICK_RE = re.compile(r"^\s*processSpy\((\d+)\)\s*;?\s*$")


def select_verified_report(
    reports: tuple[SpyReportFact, ...], *, before_ids: frozenset[str], target: str,
    requested_at: datetime, clock_tolerance_seconds: int = 30,
) -> SpyReportFact | None:
    threshold = requested_at.astimezone(timezone.utc) - timedelta(seconds=max(0, int(clock_tolerance_seconds)))
    matches = [
        report for report in reports
        if report.report_id and report.report_id not in before_ids
        and report.target == target and report.reported_at is not None
        and report.reported_at.astimezone(timezone.utc) >= threshold
    ]
    matches.sort(key=lambda item: (item.reported_at, item.report_id or ""), reverse=True)
    return matches[0] if matches else None


class V2SpyCdpBackend(ReadOnlyAccountCdpBackend):
    """Attach-only one-shot `processSpy(fleet_id)` backend."""

    def __init__(self, endpoint: str, *, game_host: str = "game.ares.nemexia.com", timeout_seconds: float = 30.0) -> None:
        super().__init__(endpoint, game_host=game_host, timeout_seconds=timeout_seconds, cache_seconds=0.0)

    async def _captcha_present(self, page) -> bool:
        return bool(await page.evaluate(r"""() => {
            const text=(document.body?.innerText||'').replace(/\s+/g,' ').toLowerCase();
            const recaptcha=!!document.querySelector(
                'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey], #recaptcha-anchor'
            );
            const botLock=typeof window.BOTCHECK_PAGE_LOCK !== 'undefined' && !!window.BOTCHECK_PAGE_LOCK;
            return recaptcha || botLock || [
                'are you human', 'защита от автоматических действий', 'humans only', 'я не робот'
            ].some(value => text.includes(value));
        }"""))

    async def _spy_row(self, fleet_id: str) -> dict[str, object]:
        page = await self._existing_fleets_page()
        if await self._captcha_present(page):
            raise SpyCaptchaBlocked("CAPTCHA обнаружена на fleets.php — действие остановлено")
        try:
            row = await page.evaluate(r"""fleetId => {
                const exact=document.getElementById(`spy1Link-${fleetId}`);
                const link=exact || Array.from(document.querySelectorAll('a[onclick]')).find(a => {
                    const value=(a.getAttribute('onclick')||'').trim();
                    return value === `processSpy(${fleetId})` || value === `processSpy(${fleetId});`;
                });
                if (!link) return null;
                const tr=link.closest('tr');
                if (!tr) return null;
                const cells=Array.from(tr.children).filter(el => el.tagName === 'TD');
                return {
                    source:cells[0]?.textContent?.trim()||'',
                    target:cells[1]?.textContent?.trim()||'',
                    onclick:link.getAttribute('onclick')||''
                };
            }""", fleet_id)
        except Exception as exc:
            raise SpyActionError("Не удалось проверить строку шпионского флота") from exc
        if not row:
            raise SpyActionError(f"Spy fleet {fleet_id} не найден среди уже загруженных строк fleets.php")
        onclick = str(row.get("onclick") or "")
        match = _PROCESS_ONCLICK_RE.fullmatch(onclick)
        if match is None or match.group(1) != fleet_id:
            raise SpyActionError("DOM action не совпадает с exact processSpy(fleet_id)")
        source = extract_coord(str(row.get("source") or ""))
        target = extract_coord(str(row.get("target") or ""))
        if source.count(":") != 2 or target.count(":") != 2:
            raise SpyActionError("Не удалось доказать source/target spy fleet из DOM")
        return {"source": source, "target": target, "onclick": onclick}

    async def _reports_ready(self) -> tuple[object, tuple[SpyReportFact, ...]]:
        page = await self._existing_options_page()
        raw = await self._read_spy_report_dom()
        if bool(raw.get("captcha_present")):
            raise SpyCaptchaBlocked("CAPTCHA обнаружена на options.php — действие остановлено")
        if not bool(raw.get("ready")):
            raise SpyActionError("Открой системные сообщения на options.php до запуска разведки")
        return page, parse_rendered_spy_reports(str(raw.get("html") or ""))

    async def _prepare_spy(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        row = await self._spy_row(command.fleet_id)
        await self._reports_ready()
        return SpyRequestPreparation(
            fleet_id=command.fleet_id, source=str(row["source"]), target=str(row["target"]),
            detail="Exact processSpy fleet row + already-rendered report source verified",
        )

    async def _request_spy(self, command: SpyRequestCommand, preparation: SpyRequestPreparation) -> SpyRequestResult:
        row = await self._spy_row(command.fleet_id)
        if str(row["source"]) != preparation.source or str(row["target"]) != preparation.target:
            raise SpyActionError("Spy fleet source/target changed after preparation")
        fleets_page = await self._existing_fleets_page()
        options_page, before_reports = await self._reports_ready()
        before_ids = frozenset(str(item.report_id) for item in before_reports if item.report_id is not None)
        requested_at = datetime.now(timezone.utc)

        # Exactly one game mutation attempt. Never call processSpy again in this method.
        try:
            await fleets_page.evaluate("""fleetId => {
                if (typeof window.processSpy !== 'function') throw new Error('processSpy missing');
                window.processSpy(Number(fleetId));
            }""", command.fleet_id)
        except Exception as exc:
            raise SpyActionError(
                "processSpy вызван, но результат вызова неоднозначен; автоматический повтор запрещён"
            ) from exc

        try:
            await asyncio.sleep(0.35)
            if await self._captcha_present(fleets_page) or await self._captcha_present(options_page):
                raise SpyCaptchaBlocked("CAPTCHA появилась после processSpy; запрос считается неоднозначным")
            await options_page.evaluate("""() => {
                if (typeof window.loadTabContent !== 'function') throw new Error('loadTabContent missing');
                window.loadTabContent('TabAdministrative', 2, 0);
            }""")
        except SpyCaptchaBlocked:
            raise
        except Exception as exc:
            raise SpyActionError(
                "Spy action мог сработать, но отчёты не удалось обновить; повтор запрещён"
            ) from exc

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.4)
            raw = await self._read_spy_report_dom()
            if bool(raw.get("captcha_present")):
                raise SpyCaptchaBlocked("CAPTCHA появилась при проверке spy report; повтор запрещён")
            if not bool(raw.get("ready")):
                raise SpyActionError("Report DOM стал недоступен после processSpy; повтор запрещён")
            reports = parse_rendered_spy_reports(str(raw.get("html") or ""))
            verified = select_verified_report(
                reports, before_ids=before_ids, target=preparation.target, requested_at=requested_at,
            )
            if verified is not None:
                return SpyRequestResult(
                    fleet_id=command.fleet_id, source=preparation.source, target=preparation.target,
                    requested_at=requested_at, verified=True, report_id=verified.report_id,
                    report_at=verified.reported_at, detail="Verified by new exact-target fresh spy report",
                )
        return SpyRequestResult(
            fleet_id=command.fleet_id, source=preparation.source, target=preparation.target,
            requested_at=requested_at, verified=False,
            detail="No new exact-target fresh report observed; automatic retry forbidden",
        )

    def prepare(self, command: SpyRequestCommand) -> SpyRequestPreparation:
        try:
            return self._submit(self._prepare_spy(command))
        except CdpReadError as exc:
            raise SpyActionError(str(exc)) from exc

    def request(self, command: SpyRequestCommand, preparation: SpyRequestPreparation) -> SpyRequestResult:
        try:
            return self._submit(self._request_spy(command, preparation))
        except CdpReadError as exc:
            raise SpyActionError(str(exc)) from exc
