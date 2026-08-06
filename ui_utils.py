from __future__ import annotations

import math
from datetime import datetime


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_clock(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%H:%M:%S")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%d.%m.%Y %H:%M:%S")


def format_number(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", " ")


def remaining(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "—"
    return format_duration(math.ceil((value - now).total_seconds()))
