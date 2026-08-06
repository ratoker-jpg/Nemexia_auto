from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

from browser import (
    BrowserAutomationError,
    BrowserWorker,
    UnverifiedSendError,
)
from models import AsteroidObservation, Target


_INSTALLED = False


def _parse_send_response(response_text: str) -> tuple[str | None, str]:
    pass_value: str | None = None
    info_value = ""
    try:
        payload = json.loads(response_text)
        raw_pass = payload.get("pass")
        if raw_pass is not None:
            pass_value = str(raw_pass).strip()
        info_value = str(payload.get("info") or "")
    except Exception:
        pass_match = re.search(r'["\']pass["\']\s*:\s*["\']?([^,"\'}\s]+)', response_text or "")
        info_match = re.search(r'["\']info["\']\s*:\s*["\']([^"\']*)', response_text or "")
        pass_value = pass_match.group(1).strip() if pass_match else None
        info_value = info_match.group(1) if info_match else ""
    return pass_value, info_value


def _raid_result(
    *,
    target: Target,
    source: str,
    ship_count: int,
    timing: dict[str, Any],
    sent_at: datetime,
    info_value: str,
    fleet_id: str | None,
    verified: bool,
) -> dict[str, Any]:
    one_way = int(timing["one"])
    round_trip = int(timing["round"])
    return {
        "fleet_id": fleet_id,
        "source": source,
        "target": target.coord,
        "player": target.player,
        "ship_count": ship_count,
        "sent_at": sent_at.isoformat(),
        "arrival_at": (sent_at + timedelta(seconds=one_way)).isoformat(),
        "return_at": (sent_at + timedelta(seconds=round_trip)).isoformat(),
        "one_way_seconds": one_way,
        "round_trip_seconds": round_trip,
        "gas_needed": timing.get("gas"),
        "server_info": info_value,
        "verified": verified,
    }


async def _send_raid_once(
    self: BrowserWorker,
    page: Any,
    target: Target,
    ship_count: int,
    home: tuple[int, int, int],
) -> dict[str, Any]:
    source = await self._prepare_fleet(page, ship_count, home)
    timing = await self._set_target(page, target)
    before_rows = await self._read_flights_from_page(page)
    before_ids = {str(item["id"]) for item in before_rows if item.get("id")}

    button = page.locator("#SendFleetButton")
    if await button.is_disabled():
        error = await self._visible_error(page)
        await self._diagnostic("raid_send_disabled")
        raise BrowserAutomationError(
            "Игра не разрешает отправку рейса."
            + (f" Ошибка игры: {error}" if error else " Проверь газ, корабли, цель и свободные слоты.")
        )

    try:
        async with page.expect_response(
            lambda response: (
                "ajax_fleets.php" in response.url
                and response.request.method == "POST"
                and "type=SendFleet" in (response.request.post_data or "")
            ),
            timeout=15_000,
        ) as response_info:
            await button.click()
        response = await response_info.value
        response_text = await response.text()
    except Exception as exc:
        await self._assert_no_captcha(page, "captcha_raid_send_response")
        error = await self._visible_error(page)
        await self._diagnostic("raid_send_no_response")
        raise BrowserAutomationError(
            f"Не получен ответ на отправку.{(' Ошибка игры: ' + error) if error else ''}"
        ) from exc

    sent_at = datetime.now().astimezone()
    pass_value, info_value = _parse_send_response(response_text)
    if pass_value == "0":
        await self._diagnostic("raid_send_rejected")
        raise BrowserAutomationError(info_value or "Игра отклонила отправку флота")
    if pass_value != "1":
        result = _raid_result(
            target=target,
            source=source,
            ship_count=ship_count,
            timing=timing,
            sent_at=sent_at,
            info_value=info_value,
            fleet_id=None,
            verified=False,
        )
        await self._diagnostic("raid_send_unknown_response")
        raise UnverifiedSendError(
            "Игра вернула неизвестный ответ на отправку. Повтор остановлен, чтобы не создать дубль.",
            result,
        )

    await asyncio.sleep(0.5)
    try:
        await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
    except Exception:
        pass

    new_row: dict[str, Any] | None = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        await asyncio.sleep(0.45)
        await self._assert_no_captcha(page, "captcha_verify_raid_send")
        rows = await self._read_flights_from_page(page)
        candidates = [
            row
            for row in rows
            if row.get("id")
            and str(row["id"]) not in before_ids
            and str(row.get("target") or "").replace(" ", "") == target.coord
            and str(row.get("mission") or "").strip().lower() == "атака"
        ]
        if candidates:
            new_row = candidates[0]
            break

    result = _raid_result(
        target=target,
        source=source,
        ship_count=ship_count,
        timing=timing,
        sent_at=sent_at,
        info_value=info_value,
        fleet_id=str(new_row.get("id")) if new_row and new_row.get("id") else None,
        verified=bool(new_row),
    )
    if not new_row:
        await self._diagnostic("raid_send_unverified")
        raise UnverifiedSendError(
            f"Игра могла принять рейс на {target.coord}, но новая строка полёта не найдена. "
            "Повтор остановлен, чтобы не создать дубль.",
            result,
        )
    return result


async def _send_asteroid_once(
    self: BrowserWorker,
    page: Any,
    observation: AsteroidObservation,
    recycler_count: int,
    home: tuple[int, int, int],
    safety_seconds: int,
) -> dict[str, Any]:
    source = await self._prepare_recycler_fleet(page, recycler_count, home)
    plan = await self._resolve_asteroid_plan(
        page,
        observation,
        safety_seconds=max(0, int(safety_seconds)),
    )
    await self._assert_no_captcha(page, "captcha_before_asteroid_send")
    before_rows = await self._read_flights_from_page(page)
    before_ids = {str(item["id"]) for item in before_rows if item.get("id")}

    button = page.locator("#SendFleetButton")
    if await button.is_disabled():
        error = await self._visible_error(page)
        await self._diagnostic("asteroid_send_disabled")
        raise BrowserAutomationError(
            "Игра не разрешает отправку на астероид."
            + (f" Ошибка игры: {error}" if error else " Проверь газ, корабли и свободные слоты.")
        )

    try:
        async with page.expect_response(
            lambda response: (
                "ajax_fleets.php" in response.url
                and response.request.method == "POST"
                and "type=SendFleet" in (response.request.post_data or "")
            ),
            timeout=15_000,
        ) as response_info:
            await button.click()
        response = await response_info.value
        response_text = await response.text()
    except Exception as exc:
        await self._assert_no_captcha(page, "captcha_asteroid_send_response")
        error = await self._visible_error(page)
        await self._diagnostic("asteroid_send_no_response")
        raise BrowserAutomationError(
            f"Не получен ответ на отправку к астероиду.{(' Ошибка игры: ' + error) if error else ''}"
        ) from exc

    sent_at = datetime.now().astimezone()
    pass_value, info_value = _parse_send_response(response_text)

    def result_for(row: dict[str, Any] | None, verified: bool) -> dict[str, Any]:
        return {
            "fleet_id": str(row.get("id")) if row and row.get("id") else None,
            "source": source,
            "target": plan.target_coord,
            "origin_coord": observation.coord,
            "player": "Астероид",
            "ship_count": recycler_count,
            "mission": "Добыча газа",
            "sent_at": sent_at.isoformat(),
            "arrival_at": (sent_at + timedelta(seconds=plan.one_way_seconds)).isoformat(),
            "return_at": (sent_at + timedelta(seconds=plan.round_trip_seconds)).isoformat(),
            "one_way_seconds": plan.one_way_seconds,
            "round_trip_seconds": plan.round_trip_seconds,
            "gas_needed": plan.gas_needed,
            "shifts": plan.shifts,
            "server_info": info_value,
            "verified": verified,
        }

    if pass_value == "0":
        await self._diagnostic("asteroid_send_rejected")
        raise BrowserAutomationError(info_value or "Игра отклонила добычу газа")
    if pass_value != "1":
        await self._diagnostic("asteroid_send_unknown_response")
        raise UnverifiedSendError(
            "Игра вернула неизвестный ответ на отправку к астероиду. "
            "Автопродление остановлено, чтобы не создать дубль.",
            result_for(None, False),
        )

    await asyncio.sleep(0.5)
    try:
        await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
    except Exception:
        pass

    new_row: dict[str, Any] | None = None
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        await asyncio.sleep(0.45)
        await self._assert_no_captcha(page, "captcha_verify_asteroid_send")
        rows = await self._read_flights_from_page(page)
        candidates = [
            row
            for row in rows
            if row.get("id")
            and str(row["id"]) not in before_ids
            and str(row.get("target") or "").replace(" ", "") == plan.target_coord
            and str(row.get("mission") or "").strip().lower() == "добыча газа"
        ]
        if candidates:
            new_row = candidates[0]
            break

    result = result_for(new_row, bool(new_row))
    if not new_row:
        await self._diagnostic("asteroid_send_unverified")
        raise UnverifiedSendError(
            "Игра могла принять рейс на астероид, но новая строка полёта не найдена. "
            "Автопродление остановлено, чтобы не создать дубль.",
            result,
        )
    return result


def install_raid_verification_fix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    BrowserWorker._send_raid_once = _send_raid_once
    BrowserWorker._send_asteroid_once = _send_asteroid_once
    _INSTALLED = True
