from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from v2.persistence.database import V2Database


class V2SettingError(ValueError):
    pass


Parser = Callable[[object], Any]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    default: object
    parser: Parser


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise V2SettingError(f"Expected boolean, got {value!r}")


def _bounded_int(minimum: int, maximum: int) -> Parser:
    def parse(value: object) -> int:
        try:
            result = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise V2SettingError(f"Expected integer, got {value!r}") from exc
        if not minimum <= result <= maximum:
            raise V2SettingError(f"Expected {minimum}..{maximum}, got {result}")
        return result

    return parse


def _coord(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    match = re.fullmatch(r"(\d+):(\d+):(\d+)", text)
    if not match or any(int(part) <= 0 for part in match.groups()):
        raise V2SettingError(f"Expected positive g:s:p coordinate, got {value!r}")
    return ":".join(str(int(part)) for part in match.groups())


SETTING_SPECS: dict[str, SettingSpec] = {
    "ui_reduce_motion": SettingSpec("ui_reduce_motion", False, _bool),
    "ui_scale_percent": SettingSpec("ui_scale_percent", 100, _bounded_int(80, 160)),
    "cdp_port": SettingSpec("cdp_port", 9222, _bounded_int(1, 65535)),
    "farm_home": SettingSpec("farm_home", "3:39:11", _coord),
    "command_planet": SettingSpec("command_planet", "2:5:6", _coord),
    "farm_return_buffer_minutes": SettingSpec(
        "farm_return_buffer_minutes", 5, _bounded_int(0, 60)
    ),
}


def _encode(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


class V2SettingsRepository:
    """Typed allow-listed settings stored only in the V2-owned database."""

    def __init__(self, database: V2Database) -> None:
        self.database = database

    def keys(self) -> tuple[str, ...]:
        return tuple(SETTING_SPECS)

    def get(self, key: str) -> object:
        spec = self._spec(key)
        raw = self.database.read_setting_raw(spec.key)
        if raw is None:
            return spec.default
        try:
            return spec.parser(raw)
        except V2SettingError:
            return spec.default

    def set(self, key: str, value: object) -> object:
        spec = self._spec(key)
        parsed = spec.parser(value)
        self.database.write_setting_raw(spec.key, _encode(parsed))
        return parsed

    def snapshot(self) -> dict[str, object]:
        return {key: self.get(key) for key in SETTING_SPECS}

    @staticmethod
    def _spec(key: str) -> SettingSpec:
        try:
            return SETTING_SPECS[str(key)]
        except KeyError as exc:
            raise V2SettingError(f"Unknown V2 setting: {key}") from exc
