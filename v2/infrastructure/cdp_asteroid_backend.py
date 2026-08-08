from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Coroutine

from v2.application.asteroid_actions import (
    AsteroidActionError,
    AsteroidCaptchaBlocked,
    AsteroidDispatchAmbiguous,
    AsteroidDispatchCommand,
    AsteroidDispatchPreparation,
    AsteroidDispatchRejected,
    AsteroidDispatchResult,
    AsteroidPreparationRejected,
)
from v2.domain.asteroids import (
    ASTEROID_MISSION_CODE,
    ASTEROID_MISSION_NAME,
    ASTEROID_PLAN_MAX_ITERATIONS,
    ASTEROID_RECYCLER_SHIP_KEY,
    AsteroidObservationFact,
    movement_margin_seconds,
    parse_asteroid_tooltip,
    predict_coordinate,
    server_wall_clock_to_utc,
)
from v2.infrastructure.cdp_asteroid_reader import ReadOnlyAsteroidCdpBackend
from v2.infrastructure.cdp_read_backend import extract_coord, parse_counter


def select_verified_asteroid_flight(
    rows: tuple[dict[str, str | None], ...],
    *,
    before_ids: frozenset[str],
    target: str,
) -> dict[str, str | None] | None:
    matches = [
        row for row in rows
        if row.get("id")
        and str(row["id"]) not in before_ids
        and extract_coord(str(row.get("target") or "")) == target
        and str(row.get("mission") or "").strip().casefold() == ASTEROID_MISSION_NAME.casefold()
    ]
    matches.sort(key=lambda row: int(str(row.get("id") or "0")), reverse=True)
    return matches[0] if matches else None


class V2AsteroidCdpBackend(ReadOnlyAsteroidCdpBackend):
    """Attach-only exactly-one-attempt asteroid SendFleet backend."""

    def __init__(
        self,
        endpoint: str,
        *,
        game_host: str = "game.ares.nemexia.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            endpoint,
            game_host=game_host,
            timeout_seconds=timeout_seconds,
            cache_seconds=0.0,
        )
        self.timeout_seconds = max(5.0, float(timeout_seconds))

    def _action_submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        """Preserve typed action outcomes instead of flattening them into read errors."""
        if self._closed or self._loop is None:
            raise AsteroidActionError("CDP asteroid backend is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=self.timeout_seconds + 1.0)
        except AsteroidActionError:
            raise
        except Exception as exc:
            future.cancel()
            raise AsteroidActionError(str(exc) or exc.__class__.__name__) from exc

    async def _existing_fleets_page(self):
        browser = await self._ensure_browser()
        pages = [page for context in browser.contexts for page in context.pages if not page.is_closed()]
        page = next(
            (item for item in pages if self.game_host in item.url and "fleets.php" in item.url),
            None,
        )
        if page is None:
            raise AsteroidActionError("Открой fleets.php в уже подключённом браузере")
        return page

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

    async def _server_now_utc(self, page) -> datetime:
        values = await page.evaluate(r"""() => {
            const d=(window.currentTime instanceof Date && !Number.isNaN(window.currentTime.getTime()))
                ? window.currentTime : null;
            return d ? [d.getFullYear(),d.getMonth()+1,d.getDate(),d.getHours(),d.getMinutes(),d.getSeconds()] : null;
        }""")
        if not values or len(values) != 6:
            raise AsteroidActionError("Не удалось доказать server currentTime")
        return server_wall_clock_to_utc(datetime(*(int(value) for value in values)))

    async def _assert_source(self, page, source: str) -> None:
        if await self._captcha_present(page):
            raise AsteroidCaptchaBlocked("CAPTCHA обнаружена на fleets.php — asteroid dispatch остановлен")
        current = str(await page.evaluate("""() => {
            const value=id => document.querySelector(id)?.value || '';
            return [value('#my_c1'), value('#my_c2'), value('#my_c3')].join(':');
        }""") or "")
        if current != source:
            raise AsteroidPreparationRejected(
                f"Сейчас выбрана планета {current or 'неизвестно'}, требуется {source}. Переключи её вручную."
            )

    async def _matching_galaxy_page(self, galaxy: int, system: int):
        browser = await self._ensure_browser()
        pages = [
            page for context in browser.contexts for page in context.pages
            if not page.is_closed() and self.game_host in page.url and "galaxy.php" in page.url
        ]
        for page in pages:
            try:
                current = await page.evaluate("""() => {
                    const url=new URL(location.href);
                    return [
                        Number(document.querySelector('#c1')?.value || url.searchParams.get('galaxy') || 0),
                        Number(document.querySelector('#c2')?.value || url.searchParams.get('solar') || 0)
                    ];
                }""")
            except Exception:
                continue
            if current and int(current[0]) == int(galaxy) and int(current[1]) == int(system):
                return page
        raise AsteroidPreparationRejected(
            f"Открой вручную galaxy.php систему {galaxy}:{system} для live re-check астероида"
        )

    async def _read_square_info(self, page, g: int, s: int, p: int) -> tuple[str, datetime]:
        if await self._captcha_present(page):
            raise AsteroidCaptchaBlocked("CAPTCHA обнаружена на galaxy.php — asteroid dispatch остановлен")
        server_now = await self._server_now_utc(page)
        try:
            response = await page.evaluate(r"""async coord => {
                const body=new URLSearchParams({
                    type:'squareInfo', c1:String(coord.g), c2:String(coord.s), c3:String(coord.p)
                }).toString();
                const result=await fetch('ajax_info.php', {
                    method:'POST', credentials:'same-origin',
                    headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}, body
                });
                return {ok:result.ok, status:result.status, text:await result.text()};
            }""", {"g": int(g), "s": int(s), "p": int(p)})
        except Exception as exc:
            raise AsteroidPreparationRejected("Не удалось повторно прочитать asteroid squareInfo") from exc
        text = str(response.get("text") or "")
        lower = text.casefold()
        if any(token in lower for token in (
            "are you human", "защита от автоматических действий", "humans only", "я не робот", "recaptcha"
        )):
            raise AsteroidCaptchaBlocked("CAPTCHA появилась при asteroid squareInfo re-check")
        if not bool(response.get("ok")):
            raise AsteroidPreparationRejected(f"squareInfo вернул HTTP {response.get('status')}")
        return text, server_now

    async def _recheck_observation(
        self,
        observation: AsteroidObservationFact,
        *,
        reference_page,
    ) -> AsteroidObservationFact:
        current_server = await self._server_now_utc(reference_page)
        try:
            current_coord, _ = predict_coordinate(observation, current_server, safety_seconds=0)
        except ValueError as exc:
            raise AsteroidPreparationRejected(str(exc)) from exc
        page = await self._matching_galaxy_page(current_coord[0], current_coord[1])
        tooltip, observed_at = await self._read_square_info(page, *current_coord)
        naive_server = observed_at.astimezone(timezone(timedelta(hours=4))).replace(tzinfo=None)
        try:
            fresh = parse_asteroid_tooltip(
                tooltip,
                galaxy=current_coord[0],
                system=current_coord[1],
                position=current_coord[2],
                observed_server_at=naive_server,
            )
        except ValueError as exc:
            raise AsteroidPreparationRejected(
                f"Asteroid trajectory больше не подтверждается на {':'.join(map(str, current_coord))}: {exc}"
            ) from exc
        if fresh.period_seconds != observation.period_seconds:
            raise AsteroidPreparationRejected("Asteroid movement period changed since observation")
        expected_next = observation.next_move_at.astimezone(timezone.utc)
        while expected_next <= observed_at:
            expected_next += timedelta(seconds=observation.period_seconds)
        if fresh.next_move_at.astimezone(timezone.utc) != expected_next:
            raise AsteroidPreparationRejected("Asteroid movement schedule changed since observation")
        return fresh

    async def _capacity_and_recyclers(self, page) -> tuple[int, int]:
        raw = await page.evaluate(r"""() => ({
            recycler:document.querySelector('#ship_1_11_max')?.value || '',
            used:document.querySelector('#FleetsCount')?.textContent || '',
            maximum:document.querySelector('#MaxFleets')?.textContent || ''
        })""")
        available = parse_counter(str(raw.get("recycler") or ""))
        used = parse_counter(str(raw.get("used") or ""))
        maximum = parse_counter(str(raw.get("maximum") or ""))
        if available is None:
            raise AsteroidPreparationRejected("Не удалось прочитать #ship_1_11_max")
        if used is None or maximum is None or maximum <= 0 or used > maximum:
            raise AsteroidPreparationRejected("Не удалось доказать live FleetsCount / MaxFleets")
        return available, maximum - used

    async def _prepare_form(self, page, command: AsteroidDispatchCommand) -> None:
        try:
            await page.evaluate("() => { if (typeof showTab === 'function') showTab('TabChooseShips'); }")
            await page.locator("#TabChooseShips").wait_for(state="visible", timeout=7_000)
            await page.locator(f"#{ASTEROID_RECYCLER_SHIP_KEY}").wait_for(state="attached", timeout=7_000)
            await page.evaluate(
                "() => document.querySelectorAll('input.ships').forEach(el => { el.value='0'; el.dispatchEvent(new Event('change', {bubbles:true})); })"
            )
            await page.locator("select#mission").select_option(ASTEROID_MISSION_CODE)
            await page.evaluate(
                "mission => { if (typeof selectMissionImg === 'function') selectMissionImg(Number(mission)); }",
                ASTEROID_MISSION_CODE,
            )
            recycler = page.locator(f"#{ASTEROID_RECYCLER_SHIP_KEY}")
            await recycler.fill(str(command.recycler_count))
            await recycler.dispatch_event("change")
            await page.evaluate(
                "() => { if (typeof shipsCheck !== 'function') throw new Error('shipsCheck missing'); shipsCheck(); }"
            )
            await page.locator("#TabSendFleets").wait_for(state="visible", timeout=12_000)
        except AsteroidActionError:
            raise
        except Exception as exc:
            raise AsteroidPreparationRejected("Не удалось безопасно подготовить recycler fleet form") from exc

    async def _calculate_plan(
        self,
        page,
        command: AsteroidDispatchCommand,
    ) -> AsteroidDispatchPreparation:
        candidate = (
            command.observation.galaxy,
            command.observation.system,
            command.observation.position,
        )
        available, free_slots = await self._capacity_and_recyclers(page)
        if available < command.recycler_count:
            raise AsteroidPreparationRejected(
                f"Недостаточно переработчиков: доступно {available}, требуется {command.recycler_count}"
            )
        if free_slots <= 0:
            raise AsteroidPreparationRejected("Нет свободных live fleet slots")

        for _ in range(ASTEROID_PLAN_MAX_ITERATIONS):
            g, s, p = candidate
            for selector, value in (("#target_c1", g), ("#target_c2", s), ("#target_c3", p)):
                locator = page.locator(selector)
                await locator.fill(str(value))
                await locator.dispatch_event("change")
            try:
                await page.evaluate(
                    "() => { if (typeof FlyCheck !== 'function') throw new Error('FlyCheck missing'); FlyCheck(); }"
                )
                await asyncio.sleep(0.2)
                timing = await page.evaluate(r"""() => {
                    const digits=value => {
                        const m=String(value||'').replace(/[^0-9]/g,'');
                        return m ? Number(m) : null;
                    };
                    return {
                        one:Number(window.seconds||0), round:Number(window.seconds2||0),
                        gas:digits(document.querySelector('#missionGasNeeded')?.textContent)
                    };
                }""")
            except Exception as exc:
                raise AsteroidPreparationRejected("Игра не рассчитала asteroid flight time") from exc
            one = int(timing.get("one") or 0)
            round_trip = int(timing.get("round") or 0)
            if one <= 0 or round_trip <= 0 or round_trip < one:
                raise AsteroidPreparationRejected("Некорректный asteroid flight timing")
            prepared_at = await self._server_now_utc(page)
            arrival_at = prepared_at + timedelta(seconds=one)
            return_at = prepared_at + timedelta(seconds=round_trip)
            try:
                predicted, shifts = predict_coordinate(command.observation, arrival_at, safety_seconds=0)
            except ValueError as exc:
                raise AsteroidPreparationRejected(str(exc)) from exc
            if predicted != candidate:
                candidate = predicted
                continue
            margin = movement_margin_seconds(
                command.observation.next_move_at,
                command.observation.period_seconds,
                arrival_at,
            )
            if margin < command.safety_seconds:
                raise AsteroidPreparationRejected(
                    f"Прибытие слишком близко к движению астероида: {margin:.1f}s < {command.safety_seconds}s"
                )
            return AsteroidDispatchPreparation(
                source=command.source,
                observation=command.observation,
                target=":".join(str(value) for value in candidate),
                recycler_count=command.recycler_count,
                available_recyclers=available,
                free_fleet_slots=free_slots,
                prepared_at=prepared_at,
                one_way_seconds=one,
                round_trip_seconds=round_trip,
                shifts=shifts,
                arrival_at=arrival_at,
                return_at=return_at,
                gas_needed=timing.get("gas"),
                movement_margin_seconds=margin,
                detail="Attach-only fleets form + deterministic asteroid timing prepared",
            )
        raise AsteroidPreparationRejected(
            f"Asteroid target не стабилизировался за {ASTEROID_PLAN_MAX_ITERATIONS} итераций"
        )

    async def _prepare_asteroid(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        page = await self._existing_fleets_page()
        await self._assert_source(page, command.source)
        await self._recheck_observation(command.observation, reference_page=page)
        await self._prepare_form(page, command)
        prepared = await self._calculate_plan(page, command)
        await self._assert_source(page, command.source)
        return prepared

    async def _read_flight_rows(self, page) -> tuple[dict[str, str | None], ...]:
        raw = await page.evaluate(r"""() => Array.from(document.querySelectorAll('#fleetHandler tbody tr')).map(row => {
            const cells=Array.from(row.children).filter(el=>el.tagName==='TD');
            const details=row.querySelector('.fleetType a');
            const onclick=details?.getAttribute('onclick')||'';
            const match=onclick.match(/fleetDetails\((\d+)\)/);
            return {
                id:match?match[1]:null,
                source:cells[0]?.textContent?.trim()||'',
                target:cells[1]?.textContent?.trim()||'',
                mission:details?.textContent?.trim()||cells[4]?.textContent?.trim()||''
            };
        })""")
        return tuple(
            {
                "id": str(item.get("id")) if item.get("id") else None,
                "source": str(item.get("source") or ""),
                "target": str(item.get("target") or ""),
                "mission": str(item.get("mission") or ""),
            }
            for item in (raw or ())
        )

    @staticmethod
    def _unverified_result(
        preparation: AsteroidDispatchPreparation,
        *,
        sent_at: datetime,
        fleet_id: str | None = None,
        detail: str = "",
    ) -> AsteroidDispatchResult:
        return AsteroidDispatchResult(
            source=preparation.source,
            observation_coord=preparation.observation.coord,
            target=preparation.target,
            recycler_count=preparation.recycler_count,
            sent_at=sent_at,
            arrival_at=sent_at + timedelta(seconds=preparation.one_way_seconds),
            return_at=sent_at + timedelta(seconds=preparation.round_trip_seconds),
            fleet_id=fleet_id,
            verified=False,
            server_info=detail,
        )

    async def _dispatch_asteroid(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        page = await self._existing_fleets_page()
        await self._assert_source(page, command.source)
        await self._recheck_observation(command.observation, reference_page=page)
        available, free_slots = await self._capacity_and_recyclers(page)
        if available < command.recycler_count:
            raise AsteroidDispatchRejected("Недостаточно переработчиков перед SendFleet")
        if free_slots <= 0:
            raise AsteroidDispatchRejected("Нет свободных fleet slots перед SendFleet")
        current_target = await page.evaluate("""() => [
            document.querySelector('#target_c1')?.value||'',
            document.querySelector('#target_c2')?.value||'',
            document.querySelector('#target_c3')?.value||''
        ].join(':')""")
        if str(current_target) != preparation.target:
            raise AsteroidDispatchRejected("Prepared target изменился до SendFleet")

        before_rows = await self._read_flight_rows(page)
        before_ids = frozenset(str(row["id"]) for row in before_rows if row.get("id"))
        button = page.locator("#SendFleetButton")
        try:
            await button.wait_for(state="visible", timeout=5_000)
            if await button.is_disabled():
                raise AsteroidDispatchRejected(
                    "Игра не разрешает SendFleet: проверь корабли, газ, координаты и fleet slots"
                )
        except AsteroidDispatchRejected:
            raise
        except Exception as exc:
            raise AsteroidDispatchRejected("SendFleetButton недоступна до remote attempt") from exc
        sent_at = await self._server_now_utc(page)

        # Exactly one remote mutation attempt. Never click SendFleet again in this method.
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
            result = self._unverified_result(
                preparation,
                sent_at=sent_at,
                detail="SendFleet мог быть принят, но response boundary не подтверждён",
            )
            raise AsteroidDispatchAmbiguous(result.server_info, result) from exc

        try:
            payload = json.loads(response_text)
        except Exception as exc:
            result = self._unverified_result(
                preparation,
                sent_at=sent_at,
                detail="SendFleet response не распознан; автоматический повтор запрещён",
            )
            raise AsteroidDispatchAmbiguous(result.server_info, result) from exc
        pass_value = str(payload.get("pass"))
        server_info = str(payload.get("info") or "")
        if pass_value == "0":
            raise AsteroidDispatchRejected(server_info or "Игра явно отклонила asteroid SendFleet")
        if pass_value not in {"1", "True", "true"}:
            result = self._unverified_result(
                preparation,
                sent_at=sent_at,
                detail=server_info or "SendFleet response неоднозначен",
            )
            raise AsteroidDispatchAmbiguous(result.server_info, result)

        try:
            await page.evaluate("() => { if (typeof showFleets === 'function') showFleets(); }")
        except Exception:
            pass
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.4)
            rows = await self._read_flight_rows(page)
            verified = select_verified_asteroid_flight(
                rows,
                before_ids=before_ids,
                target=preparation.target,
            )
            if verified is not None:
                return AsteroidDispatchResult(
                    source=preparation.source,
                    observation_coord=preparation.observation.coord,
                    target=preparation.target,
                    recycler_count=preparation.recycler_count,
                    sent_at=sent_at,
                    arrival_at=sent_at + timedelta(seconds=preparation.one_way_seconds),
                    return_at=sent_at + timedelta(seconds=preparation.round_trip_seconds),
                    fleet_id=str(verified["id"]),
                    verified=True,
                    server_info=server_info,
                )
            if await self._captcha_present(page):
                break
        result = self._unverified_result(
            preparation,
            sent_at=sent_at,
            detail=server_info or "Новая exact-target flight row Добыча газа не подтверждена",
        )
        raise AsteroidDispatchAmbiguous(
            "Asteroid SendFleet мог быть принят, но exact new-flight verification отсутствует",
            result,
        )

    def prepare(self, command: AsteroidDispatchCommand) -> AsteroidDispatchPreparation:
        return self._action_submit(self._prepare_asteroid(command))

    def dispatch(
        self,
        command: AsteroidDispatchCommand,
        preparation: AsteroidDispatchPreparation,
    ) -> AsteroidDispatchResult:
        return self._action_submit(self._dispatch_asteroid(command, preparation))
