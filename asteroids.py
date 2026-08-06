from __future__ import annotations

import html as html_module
import re
from datetime import datetime, timedelta

from models import AsteroidObservation

SERVER_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M",
)


def parse_server_datetime(value: str) -> datetime:
    normalized = " ".join(html_module.unescape(value or "").replace("\xa0", " ").split())
    for fmt in SERVER_DATETIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    raise ValueError(f"Не удалось разобрать серверное время: {value!r}")


def parse_asteroid_tooltip(
    tooltip_html: str,
    g: int,
    s: int,
    p: int,
    scanned_server_at: datetime,
) -> AsteroidObservation:
    text = re.sub(r"<[^>]+>", " ", tooltip_html or "")
    text = " ".join(html_module.unescape(text).replace("\xa0", " ").split())
    if not re.search(r"информац\w*\s+об\s+астероид", text, re.I):
        raise ValueError("Ответ клетки не содержит информацию об астероиде")

    last_match = re.search(
        r"Последнее\s+перемещение\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.I,
    )
    next_match = re.search(
        r"Следующее\s+перемещение\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
        text,
        re.I,
    )
    speed_match = re.search(r"Скорость\s+(\d+)\s*Минут", text, re.I)
    if not last_match or not next_match:
        raise ValueError("В подсказке отсутствует время перемещения астероида")

    last_move = parse_server_datetime(last_match.group(1))
    next_move = parse_server_datetime(next_match.group(1))
    period_seconds = int((next_move - last_move).total_seconds())
    if period_seconds <= 0 and speed_match:
        period_seconds = int(speed_match.group(1)) * 60
    if period_seconds <= 0:
        raise ValueError("Некорректный период перемещения астероида")

    # A saved tooltip can be read a fraction after the announced boundary. Move the
    # schedule forward, while the coordinate still represents the visible current cell.
    while next_move <= scanned_server_at:
        last_move = next_move
        next_move += timedelta(seconds=period_seconds)

    return AsteroidObservation(
        g=int(g),
        s=int(s),
        p=int(p),
        last_move_server=last_move,
        next_move_server=next_move,
        period_seconds=period_seconds,
        scanned_server_at=scanned_server_at,
        tooltip_html=tooltip_html,
    )


def advance_coordinate(
    g: int,
    s: int,
    p: int,
    steps: int,
    *,
    max_system: int = 40,
) -> tuple[int, int, int]:
    if min(g, s, p) <= 0 or p > 24 or max_system <= 0:
        raise ValueError("Некорректные координаты астероида")
    if steps < 0:
        raise ValueError("Обратное движение астероидов не поддерживается")
    linear = (s - 1) * 24 + (p - 1) + steps
    new_system, position_zero = divmod(linear, 24)
    new_system += 1
    if new_system > max_system:
        raise ValueError(f"Астероид выходит за пределы {max_system}-й солнечной системы")
    return int(g), int(new_system), int(position_zero + 1)


def movement_count(
    next_move_server: datetime,
    period_seconds: int,
    arrival_server_at: datetime,
    *,
    safety_seconds: int = 0,
) -> int:
    if period_seconds <= 0:
        raise ValueError("Период движения должен быть больше нуля")
    effective_arrival = arrival_server_at + timedelta(seconds=max(0, int(safety_seconds)))
    if effective_arrival < next_move_server:
        return 0
    elapsed = (effective_arrival - next_move_server).total_seconds()
    return 1 + int(elapsed // period_seconds)



def movement_margin_seconds(
    next_move_server: datetime,
    period_seconds: int,
    arrival_server_at: datetime,
) -> float:
    """Distance from arrival to the nearest asteroid movement boundary."""
    if period_seconds <= 0:
        raise ValueError("Период движения должен быть больше нуля")
    if arrival_server_at < next_move_server:
        return (next_move_server - arrival_server_at).total_seconds()
    elapsed = (arrival_server_at - next_move_server).total_seconds()
    remainder = elapsed % period_seconds
    return min(remainder, period_seconds - remainder)

def predict_coordinate(
    observation: AsteroidObservation,
    arrival_server_at: datetime,
    *,
    safety_seconds: int = 0,
    max_system: int = 40,
) -> tuple[tuple[int, int, int], int]:
    shifts = movement_count(
        observation.next_move_server,
        observation.period_seconds,
        arrival_server_at,
        safety_seconds=safety_seconds,
    )
    return advance_coordinate(
        observation.g,
        observation.s,
        observation.p,
        shifts,
        max_system=max_system,
    ), shifts
