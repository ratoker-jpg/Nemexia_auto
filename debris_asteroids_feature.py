from __future__ import annotations

import asyncio
import html as html_module
import re
import threading
from datetime import datetime
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox

from app import (
    APP_NAME,
    BG,
    BORDER,
    MUTED,
    PANEL,
    PANEL_ALT,
    RED,
    TEXT,
    make_button,
)
from asteroids import parse_asteroid_tooltip
from browser import (
    BrowserAutomationError,
    BrowserWorker,
    CaptchaRequiredError,
    UnverifiedSendError,
)
from models import AsteroidObservation, parse_dt
from ui_utils import format_duration


DEBRIS_MARKER = "содержит обломки"
TOTAL_DEBRIS_SYSTEMS = 3 * 40
_INSTALLED = False


def asteroid_has_debris(tooltip_html: str) -> bool:
    """Return whether the asteroid tooltip marks the asteroid as containing debris."""
    text = re.sub(r"<[^>]+>", " ", tooltip_html or "")
    text = " ".join(html_module.unescape(text).replace("\xa0", " ").casefold().split())
    return DEBRIS_MARKER in text


def debris_scan_sequence() -> list[tuple[int, int]]:
    """Scan every supported galaxy and every solar system from 40 down to 1."""
    return [(galaxy, solar) for galaxy in range(1, 4) for solar in range(40, 0, -1)]


def _ensure_debris_table(db: Any) -> None:
    db.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS debris_asteroids(
            coord TEXT PRIMARY KEY,
            g INTEGER NOT NULL,
            s INTEGER NOT NULL,
            p INTEGER NOT NULL,
            last_move_server TEXT NOT NULL,
            next_move_server TEXT NOT NULL,
            period_seconds INTEGER NOT NULL,
            scanned_server_at TEXT NOT NULL,
            tooltip_html TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.conn.commit()


def _replace_debris_observations(db: Any, observations: list[AsteroidObservation]) -> None:
    _ensure_debris_table(db)
    with db.conn:
        db.conn.execute("DELETE FROM debris_asteroids")
        for observation in observations:
            db.conn.execute(
                """
                INSERT INTO debris_asteroids(
                    coord,g,s,p,last_move_server,next_move_server,period_seconds,
                    scanned_server_at,tooltip_html,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation.coord,
                    int(observation.g),
                    int(observation.s),
                    int(observation.p),
                    observation.last_move_server.isoformat(),
                    observation.next_move_server.isoformat(),
                    int(observation.period_seconds),
                    observation.scanned_server_at.isoformat(),
                    observation.tooltip_html,
                    datetime.now().astimezone().isoformat(),
                ),
            )


def _load_debris_observations(db: Any) -> list[AsteroidObservation]:
    _ensure_debris_table(db)
    rows = db.conn.execute(
        "SELECT * FROM debris_asteroids ORDER BY g, s, p"
    ).fetchall()
    observations: list[AsteroidObservation] = []
    for row in rows:
        last_move = parse_dt(row["last_move_server"])
        next_move = parse_dt(row["next_move_server"])
        scanned_at = parse_dt(row["scanned_server_at"])
        if not last_move or not next_move or not scanned_at:
            continue
        observations.append(
            AsteroidObservation(
                g=int(row["g"]),
                s=int(row["s"]),
                p=int(row["p"]),
                last_move_server=last_move.replace(tzinfo=None),
                next_move_server=next_move.replace(tzinfo=None),
                period_seconds=int(row["period_seconds"]),
                scanned_server_at=scanned_at.replace(tzinfo=None),
                tooltip_html=row["tooltip_html"] or "",
                status="debris",
            )
        )
    return observations


async def _scan_all_debris_asteroids(
    self: BrowserWorker,
    *,
    home: tuple[int, int, int],
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    sequence = debris_scan_sequence()
    page = await self._ensure_galaxy_page(home, sequence[0][0], sequence[0][1])
    observations: list[AsteroidObservation] = []
    seen: set[str] = set()
    scanned_systems = 0

    for index, (galaxy, solar) in enumerate(sequence, start=1):
        if cancelled and cancelled():
            return {
                "observations": observations,
                "scanned_systems": scanned_systems,
                "total_systems": len(sequence),
                "cancelled": True,
            }
        if index > 1:
            await self._load_galaxy_system(page, galaxy, solar)
        await self._assert_no_captcha(page, "captcha_debris_scan")
        scanned_systems += 1
        if progress:
            progress(
                f"Обломки: галактика {galaxy}/3 · система {solar}/40 · "
                f"проверено {scanned_systems}/{len(sequence)} · найдено {len(observations)}"
            )
        server_now = await self._server_now(page)
        links = await self._read_asteroid_links(page)
        for g, s, p in links:
            coord = f"{g}:{s}:{p}"
            if coord in seen:
                continue
            seen.add(coord)
            try:
                tooltip = await self._fetch_asteroid_info(page, g, s, p)
                if not asteroid_has_debris(tooltip):
                    continue
                observation = parse_asteroid_tooltip(tooltip, g, s, p, server_now)
                observation.status = "debris"
            except CaptchaRequiredError:
                raise
            except Exception:
                continue
            observations.append(observation)
            if progress:
                progress(f"Найден астероид с обломками {coord} · всего {len(observations)}")
        # Keep the full 120-system scan deliberate instead of hammering the galaxy endpoint.
        await asyncio.sleep(0.15)

    return {
        "observations": observations,
        "scanned_systems": scanned_systems,
        "total_systems": len(sequence),
        "cancelled": False,
    }


def _build_debris_page(self: Any) -> None:
    page = self._new_page("debris")

    controls = self._section(
        page,
        "Астероиды с обломками",
        "сканирование галактик 1–3, систем 40…1; отправка использует сохранённый скан",
    )
    controls.pack(fill="x", pady=(0, 12))

    row = tk.Frame(controls, bg=PANEL, padx=14, pady=10)
    row.pack(fill="x")

    recycler_block = tk.Frame(row, bg=PANEL)
    recycler_block.pack(side="left", padx=(0, 18))
    tk.Label(
        recycler_block,
        text="Переработчиков / рейс",
        bg=PANEL,
        fg=MUTED,
        font=("Segoe UI", 8),
    ).pack(anchor="w")
    tk.Spinbox(
        recycler_block,
        from_=1,
        to=1000,
        textvariable=self.debris_recyclers_var,
        width=7,
        bg=PANEL_ALT,
        fg=TEXT,
        buttonbackground=PANEL_ALT,
        insertbackground=TEXT,
        relief="flat",
    ).pack(anchor="w", pady=(4, 0), ipady=4)

    safety_block = tk.Frame(row, bg=PANEL)
    safety_block.pack(side="left", padx=(0, 18))
    tk.Label(
        safety_block,
        text="Запас до движения, сек",
        bg=PANEL,
        fg=MUTED,
        font=("Segoe UI", 8),
    ).pack(anchor="w")
    tk.Spinbox(
        safety_block,
        from_=0,
        to=300,
        textvariable=self.asteroid_safety_var,
        width=7,
        bg=PANEL_ALT,
        fg=TEXT,
        buttonbackground=PANEL_ALT,
        insertbackground=TEXT,
        relief="flat",
    ).pack(anchor="w", pady=(4, 0), ipady=4)

    make_button(
        row,
        "Сканировать все галактики",
        self.scan_debris_asteroids,
        "primary",
    ).pack(side="left", padx=6, pady=(14, 0))
    make_button(
        row,
        "Отправить выбранные",
        self.send_selected_debris_asteroids,
        "success",
    ).pack(side="left", padx=6, pady=(14, 0))
    make_button(
        row,
        "Остановить",
        self.cancel_debris_operation,
        "danger",
    ).pack(side="left", padx=6, pady=(14, 0))

    tk.Label(
        row,
        textvariable=self.debris_status_var,
        bg=PANEL,
        fg=MUTED,
        font=("Segoe UI Semibold", 9),
    ).pack(side="right", padx=(12, 0), pady=(14, 0))

    stats = tk.Frame(page, bg=BG)
    stats.pack(fill="x", pady=(0, 12))
    for column in range(3):
        stats.grid_columnconfigure(column, weight=1)
    self._card(stats, "ПРОВЕРЕНО СИСТЕМ", self.debris_scanned_var, "из 120").grid(
        row=0, column=0, sticky="ew", padx=(0, 8)
    )
    self._card(stats, "НАЙДЕНО С ОБЛОМКАМИ", self.debris_found_var, "последний полный скан").grid(
        row=0, column=1, sticky="ew", padx=8
    )
    self._card(stats, "ОТПРАВЛЕНО", self.debris_sent_var, "последняя операция").grid(
        row=0, column=2, sticky="ew", padx=(8, 0)
    )

    panel = self._section(
        page,
        "Найденные астероиды с обломками",
        "выдели одну или несколько строк; координаты при прилёте рассчитываются перед каждой отправкой",
    )
    panel.pack(fill="both", expand=True)
    frame = tk.Frame(panel, bg=PANEL, padx=8, pady=8)
    frame.pack(fill="both", expand=True)
    columns = ("coord", "scanned", "next", "period", "target", "one", "return", "status")
    self.debris_tree, scroll = self._tree(
        frame,
        columns,
        {
            "coord": "Найден",
            "scanned": "Время скана",
            "next": "След. движение",
            "period": "Период",
            "target": "Цель при отправке",
            "one": "Полёт туда",
            "return": "Полный цикл",
            "status": "Статус",
        },
        {
            "coord": 95,
            "scanned": 145,
            "next": 145,
            "period": 90,
            "target": 110,
            "one": 95,
            "return": 105,
            "status": 260,
        },
        selectmode="extended",
    )
    self.debris_tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    self.debris_tree.tag_configure("sent", background="#15312a")
    self.debris_tree.tag_configure("error", background="#44212a")


def _find_sidebar(self: Any) -> tk.Misc | None:
    for child in self.winfo_children():
        try:
            info = child.grid_info()
            if int(info.get("row", -1)) == 0 and int(info.get("column", -1)) == 0:
                return child
        except Exception:
            continue
    return None


def _add_debris_navigation(self: Any) -> None:
    sidebar = _find_sidebar(self)
    if sidebar is None:
        self.logger.warning("Не добавлена навигация «Обломки»: боковая панель не найдена")
        return

    def open_page() -> None:
        self.show_page("debris")
        self.page_title_var.set("Астероиды с обломками")

    button = tk.Button(
        sidebar,
        text="◇  Обломки",
        anchor="w",
        command=open_page,
        bg="#0b1220",
        fg=MUTED,
        activebackground=PANEL_ALT,
        activeforeground=TEXT,
        relief="flat",
        bd=0,
        padx=18,
        pady=12,
        cursor="hand2",
        highlightthickness=0,
        font=("Segoe UI Semibold", 10),
    )
    button.pack(fill="x", padx=10, pady=3)
    self.nav_buttons["debris"] = button


def _render_debris_asteroids(self: Any) -> None:
    if not hasattr(self, "debris_tree"):
        return
    children = self.debris_tree.get_children()
    if children:
        self.debris_tree.delete(*children)
    self._debris_iid_map = {}
    for index, observation in enumerate(self.debris_observations, start=1):
        iid = f"d:{index}"
        self._debris_iid_map[iid] = observation
        result = self.debris_result_by_origin.get(observation.coord)
        if result:
            verified = bool(result.get("verified", True))
            target = str(result.get("target") or "—")
            one = format_duration(result.get("one_way_seconds"))
            round_trip = format_duration(result.get("round_trip_seconds"))
            status = "Отправлен" if verified else "Не подтверждён"
            tag = "sent" if verified else "error"
        else:
            target = "—"
            one = "—"
            round_trip = "—"
            status = "Готов к расчёту и отправке"
            tag = ""
        self.debris_tree.insert(
            "",
            "end",
            iid=iid,
            values=(
                observation.coord,
                self._format_server_datetime(observation.scanned_server_at),
                self._format_server_datetime(observation.next_move_server),
                format_duration(observation.period_seconds),
                target,
                one,
                round_trip,
                status,
            ),
            tags=(tag,) if tag else (),
        )
    self.debris_found_var.set(str(len(self.debris_observations)))


def _debris_progress(self: Any, text: str) -> None:
    try:
        self.after(0, lambda value=text: self.debris_status_var.set(value))
    except Exception:
        pass


def _debris_home(self: Any) -> tuple[int, int, int]:
    return (
        self._safe_int(self.asteroid_home_g_var, 3),
        self._safe_int(self.asteroid_home_s_var, 39),
        self._safe_int(self.asteroid_home_p_var, 8),
    )


def _scan_debris_asteroids(self: Any) -> None:
    if self.auto_var.get() or self.asteroid_auto_var.get():
        messagebox.showerror(
            APP_NAME,
            "Останови обычную автоотправку и астероидное автопродление перед полным сканированием.",
        )
        return
    self.debris_cancel_event.clear()
    self.debris_result_by_origin = {}
    endpoint = self.endpoint()
    home = _debris_home(self)
    self.db.set_setting("debris_recyclers", max(1, self._safe_int(self.debris_recyclers_var, 100)))

    async def operation() -> dict[str, Any]:
        await self.worker.connect(endpoint)
        return await self.worker.scan_all_debris_asteroids(
            home=home,
            cancelled=self.debris_cancel_event.is_set,
            progress=lambda text: _debris_progress(self, text),
        )

    def success(payload: dict[str, Any]) -> None:
        observations = list(payload.get("observations") or [])
        scanned = int(payload.get("scanned_systems") or 0)
        total = int(payload.get("total_systems") or TOTAL_DEBRIS_SYSTEMS)
        cancelled = bool(payload.get("cancelled"))
        self.debris_observations = observations
        self.debris_scanned_var.set(f"{scanned} / {total}")
        self.debris_found_var.set(str(len(observations)))
        if not cancelled:
            _replace_debris_observations(self.db, observations)
            self.debris_status_var.set(f"Все галактики просканированы · найдено {len(observations)}")
            self.status_var.set(f"Обломки: найдено {len(observations)}")
            messagebox.showinfo(
                APP_NAME,
                f"Просканировано систем: {scanned}\nАстероидов с обломками: {len(observations)}",
            )
        else:
            self.debris_status_var.set(
                f"Сканирование остановлено · {scanned}/{total} · найдено {len(observations)}"
            )
        self.logger.info(
            "Обломки: проверено систем=%s/%s, найдено=%s, остановлено=%s",
            scanned,
            total,
            len(observations),
            cancelled,
        )
        _render_debris_asteroids(self)

    def error(exc: Exception) -> None:
        self.debris_status_var.set(f"Ошибка: {exc}")
        messagebox.showerror(APP_NAME, str(exc))

    self.run_task(operation(), "Обломки: сканирование 120 систем…", success, error)


def _selected_debris_observations(self: Any) -> list[AsteroidObservation]:
    selected: list[AsteroidObservation] = []
    for iid in self.debris_tree.selection():
        observation = self._debris_iid_map.get(iid)
        if observation is not None:
            selected.append(observation)
    return selected


def _send_selected_debris_asteroids(self: Any) -> None:
    observations = _selected_debris_observations(self)
    if not observations:
        messagebox.showinfo(APP_NAME, "Выдели в списке один или несколько астероидов с обломками")
        return
    if self.auto_var.get() or self.asteroid_auto_var.get():
        messagebox.showerror(
            APP_NAME,
            "Останови обычную автоотправку и астероидное автопродление перед отправкой на обломки.",
        )
        return

    recycler_count = max(1, self._safe_int(self.debris_recyclers_var, 100))
    safety_seconds = max(0, self._safe_int(self.asteroid_safety_var, 10))
    preview = "\n".join(f"{index}. {item.coord}" for index, item in enumerate(observations[:15], start=1))
    extra = "" if len(observations) <= 15 else f"\n…ещё {len(observations) - 15}"
    if not messagebox.askyesno(
        APP_NAME,
        f"Отправить рейсы на выбранные астероиды с обломками: {len(observations)}?\n"
        f"По {recycler_count} переработчиков на каждый рейс.\n\n{preview}{extra}\n\n"
        "Будет использован сохранённый скан. Координаты при прилёте и время будут рассчитаны заново.",
    ):
        return

    self.debris_cancel_event.clear()
    endpoint = self.endpoint()
    home = _debris_home(self)
    max_slots = self._safe_int(self.max_slots_var, 15)
    self.db.set_setting("debris_recyclers", recycler_count)

    async def operation() -> dict[str, Any]:
        await self.worker.connect(endpoint)
        flights = await self.worker.sync_all_flights()
        free_slots = max(0, int(max_slots) - len(flights))
        available = await self.worker.available_recyclers(home)
        if len(observations) > free_slots:
            raise BrowserAutomationError(
                f"Выбрано рейсов: {len(observations)}, свободных слотов: {free_slots}."
            )
        required = len(observations) * recycler_count
        if required > available:
            raise BrowserAutomationError(
                f"Для выбранных рейсов требуется {required} переработчиков, доступно {available}."
            )

        results: list[dict[str, Any]] = []
        error_text: str | None = None
        for index, observation in enumerate(observations, start=1):
            if self.debris_cancel_event.is_set():
                error_text = "Операция остановлена пользователем"
                break
            _debris_progress(
                self,
                f"Обломки: отправка {index}/{len(observations)} · {observation.coord}",
            )
            try:
                result = await self.worker.send_asteroid(
                    observation,
                    recycler_count,
                    home,
                    safety_seconds,
                )
                result["player"] = "Астероид с обломками"
                result["debris"] = True
                results.append(result)
            except UnverifiedSendError as exc:
                result = dict(exc.result)
                result["player"] = "Астероид с обломками"
                result["debris"] = True
                results.append(result)
                error_text = str(exc)
                break
            except (CaptchaRequiredError, BrowserAutomationError) as exc:
                error_text = str(exc)
                break
            except Exception as exc:
                error_text = str(exc)
                break
        return {
            "results": results,
            "error": error_text,
            "selected": len(observations),
            "free_slots": free_slots,
            "available_recyclers": available,
        }

    def success(payload: dict[str, Any]) -> None:
        results = list(payload.get("results") or [])
        error_text = str(payload.get("error") or "").strip() or None
        sent = 0
        for result in results:
            verified = bool(result.get("verified", True))
            self.db.add_asteroid_flight(
                result,
                cycle_id=None,
                status="sent" if verified else "unverified",
                error=None if verified else (error_text or "Отправка не подтверждена"),
            )
            self.debris_result_by_origin[str(result.get("origin_coord") or "")] = result
            if verified:
                sent += 1
        self.debris_sent_var.set(str(sent))
        _render_debris_asteroids(self)
        if error_text:
            self.debris_status_var.set(f"Остановка: {error_text}")
            messagebox.showerror(
                APP_NAME,
                f"Подтверждено рейсов: {sent}\nОстановка:\n{error_text}",
            )
        else:
            self.debris_status_var.set(f"Отправлено рейсов на обломки: {sent}")
            self.status_var.set(f"Обломки: отправлено {sent}")
            messagebox.showinfo(APP_NAME, f"Отправлено и подтверждено рейсов: {sent}")
        self.sync_flights(silent=True)

    def error(exc: Exception) -> None:
        self.debris_status_var.set(f"Ошибка: {exc}")
        messagebox.showerror(APP_NAME, str(exc))

    self.run_task(
        operation(),
        f"Обломки: отправка рейсов {len(observations)}…",
        success,
        error,
    )


def _cancel_debris_operation(self: Any) -> None:
    self.debris_cancel_event.set()
    self.debris_status_var.set("Остановка запрошена…")
    self.status_var.set("Остановка операции с обломками…")


def install_debris_asteroid_feature(app_class: type[Any]) -> None:
    """Install one cohesive debris scan, list and send feature."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_build_shell = app_class._build_shell
    original_render_all = app_class.render_all

    def build_shell(self: Any) -> None:
        _ensure_debris_table(self.db)
        self.debris_recyclers_var = tk.IntVar(
            value=int(self.settings.get("debris_recyclers", 100))
        )
        self.debris_status_var = tk.StringVar(value="Готов к полному сканированию")
        self.debris_scanned_var = tk.StringVar(value=f"0 / {TOTAL_DEBRIS_SYSTEMS}")
        self.debris_found_var = tk.StringVar(value="0")
        self.debris_sent_var = tk.StringVar(value="0")
        self.debris_cancel_event = threading.Event()
        self.debris_observations = _load_debris_observations(self.db)
        self.debris_result_by_origin: dict[str, dict[str, Any]] = {}
        self._debris_iid_map: dict[str, AsteroidObservation] = {}

        original_build_shell(self)
        _build_debris_page(self)
        _add_debris_navigation(self)
        if self.debris_observations:
            self.debris_status_var.set(
                f"Загружен сохранённый скан · найдено {len(self.debris_observations)}"
            )

    def render_all(self: Any) -> None:
        original_render_all(self)
        _render_debris_asteroids(self)

    BrowserWorker.scan_all_debris_asteroids = _scan_all_debris_asteroids
    app_class._build_shell = build_shell
    app_class.render_all = render_all
    app_class.scan_debris_asteroids = _scan_debris_asteroids
    app_class.send_selected_debris_asteroids = _send_selected_debris_asteroids
    app_class.cancel_debris_operation = _cancel_debris_operation
    app_class.render_debris_asteroids = _render_debris_asteroids

    _INSTALLED = True
