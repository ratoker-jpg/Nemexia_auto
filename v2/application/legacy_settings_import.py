from __future__ import annotations

from dataclasses import dataclass

from v2.application.read_store import ReadOnlyStore
from v2.application.v2_settings import SETTING_SPECS, V2SettingError, V2SettingsRepository


@dataclass(frozen=True)
class LegacyImportCandidate:
    target_key: str
    legacy_source: str
    raw_value: str
    parsed_value: object


@dataclass(frozen=True)
class LegacySettingsImportResult:
    imported: tuple[str, ...]
    skipped_existing: tuple[str, ...]
    rejected: tuple[str, ...]


class LegacySettingsImporter:
    """Copy a tiny allow-list from query-only legacy SQLite into V2-owned settings."""

    def __init__(self, source: ReadOnlyStore, target: V2SettingsRepository) -> None:
        self.source = source
        self.target = target

    def preview(self) -> tuple[tuple[LegacyImportCandidate, ...], tuple[str, ...]]:
        raw_candidates: list[tuple[str, str, str | None]] = [
            ("cdp_port", "port", self.source.get_setting("port")),
            (
                "farm_return_buffer_minutes",
                "farm_return_buffer_minutes",
                self.source.get_setting("farm_return_buffer_minutes"),
            ),
        ]

        home_parts = tuple(self.source.get_setting(f"home_{axis}") for axis in ("g", "s", "p"))
        if all(part is not None and str(part).strip() for part in home_parts):
            raw_candidates.append(
                ("farm_home", "home_g/home_s/home_p", ":".join(str(part) for part in home_parts))
            )

        candidates: list[LegacyImportCandidate] = []
        rejected: list[str] = []
        for target_key, source_key, raw in raw_candidates:
            if raw is None or not str(raw).strip():
                continue
            spec = SETTING_SPECS[target_key]
            try:
                parsed = spec.parser(raw)
            except V2SettingError:
                rejected.append(target_key)
                continue
            candidates.append(
                LegacyImportCandidate(
                    target_key=target_key,
                    legacy_source=source_key,
                    raw_value=str(raw),
                    parsed_value=parsed,
                )
            )
        return tuple(candidates), tuple(rejected)

    def import_missing(self) -> LegacySettingsImportResult:
        candidates, rejected = self.preview()
        imported: list[str] = []
        skipped: list[str] = []
        for candidate in candidates:
            if self.target.database.read_setting_raw(candidate.target_key) is not None:
                skipped.append(candidate.target_key)
                continue
            self.target.set(candidate.target_key, candidate.parsed_value)
            imported.append(candidate.target_key)
        return LegacySettingsImportResult(
            imported=tuple(imported),
            skipped_existing=tuple(skipped),
            rejected=rejected,
        )
