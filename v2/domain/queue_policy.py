from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Sequence

from v2.domain.recon import (
    LEGACY_AUTOFARM_MINERALS_MINIMUM,
    LEGACY_METAL_QUEUE_MINIMUM,
    LEGACY_SPY_REPORT_LOOKBACK_HOURS,
)


QueueMode = Literal["metal", "minerals", "autofarm"]
PROTECTED_QUEUE_STATES = frozenset({"sending", "sent", "ambiguous"})
REPLACEABLE_QUEUE_STATES = frozenset({"queued", "failed", "skipped"})


class QueueSkipReason(str, Enum):
    DISABLED = "disabled"
    BLACKLISTED = "blacklisted"
    NO_VERIFIED_REPORT = "no_verified_report"
    STALE_REPORT = "stale_report"
    ACTIVE_TARGET = "active_target"
    METAL_BELOW_MINIMUM = "metal_below_minimum"
    MINERALS_MISSING = "minerals_missing"
    AUTOFARM_BELOW_MINIMUM = "autofarm_below_minimum"
    PROTECTED_EXISTING = "protected_existing"
    OUTSIDE_LIMIT = "outside_limit"
    DUPLICATE_INPUT = "duplicate_input"


@dataclass(frozen=True)
class QueueTargetFact:
    coord: str
    player: str
    enabled: bool
    blacklisted: bool
    report_id: str | None
    reported_at: datetime | None
    metal: int | None
    minerals: int | None
    gas: int | None


@dataclass(frozen=True)
class ExistingQueueFact:
    id: int
    position: int
    state: str
    coord: str


@dataclass(frozen=True)
class QueueDesiredRow:
    position: int
    coord: str
    player: str
    metal: int | None
    minerals: int | None
    gas: int | None
    last_spy_at: str
    enabled: bool = True
    blacklisted: bool = False


@dataclass(frozen=True)
class QueueSkippedFact:
    coord: str
    reason: QueueSkipReason


@dataclass(frozen=True)
class QueueRefillPreview:
    mode: QueueMode
    queue_size: int
    desired: tuple[QueueDesiredRow, ...]
    added: tuple[str, ...]
    kept: tuple[str, ...]
    removed: tuple[str, ...]
    protected: tuple[str, ...]
    skipped: tuple[QueueSkippedFact, ...]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _report_fresh(report_at: datetime | None, *, now: datetime, lookback_hours: int) -> bool:
    if report_at is None:
        return False
    return _as_utc(report_at) >= _as_utc(now) - timedelta(hours=max(1, int(lookback_hours)))


def _rank_key(item: QueueTargetFact, mode: QueueMode):
    if mode == "metal":
        return (-int(item.metal or 0), item.coord)
    if mode == "minerals":
        return (-int(item.minerals or 0), item.coord)
    if mode == "autofarm":
        return (-int(item.minerals or 0), -int(item.metal or 0), item.coord)
    raise ValueError(f"Unsupported queue mode: {mode}")


def _eligibility_reason(
    item: QueueTargetFact,
    mode: QueueMode,
    *,
    now: datetime,
    active_targets: frozenset[str],
    minimum_metal: int,
    lookback_hours: int,
) -> QueueSkipReason | None:
    if not item.enabled:
        return QueueSkipReason.DISABLED
    if item.blacklisted:
        return QueueSkipReason.BLACKLISTED
    if not str(item.report_id or "").strip() or item.reported_at is None:
        return QueueSkipReason.NO_VERIFIED_REPORT
    if not _report_fresh(item.reported_at, now=now, lookback_hours=lookback_hours):
        return QueueSkipReason.STALE_REPORT
    if item.coord in active_targets:
        return QueueSkipReason.ACTIVE_TARGET
    if mode == "metal":
        if item.metal is None or int(item.metal) < max(0, int(minimum_metal)):
            return QueueSkipReason.METAL_BELOW_MINIMUM
    elif mode == "minerals":
        if item.minerals is None:
            return QueueSkipReason.MINERALS_MISSING
    elif mode == "autofarm":
        if item.minerals is None or int(item.minerals) < LEGACY_AUTOFARM_MINERALS_MINIMUM:
            return QueueSkipReason.AUTOFARM_BELOW_MINIMUM
    else:
        raise ValueError(f"Unsupported queue mode: {mode}")
    return None


def build_queue_refill_preview(
    targets: Sequence[QueueTargetFact],
    existing: Sequence[ExistingQueueFact],
    *,
    mode: QueueMode,
    now: datetime,
    queue_size: int = 45,
    minimum_metal: int = LEGACY_METAL_QUEUE_MINIMUM,
    lookback_hours: int = LEGACY_SPY_REPORT_LOOKBACK_HOURS,
    active_targets: Sequence[str] = (),
) -> QueueRefillPreview:
    """Pure deterministic queue policy. No browser or persistence access."""

    size = max(1, int(queue_size))
    active = frozenset(str(coord) for coord in active_targets)
    protected_coords = frozenset(
        item.coord for item in existing if item.state in PROTECTED_QUEUE_STATES
    )
    existing_queued = frozenset(item.coord for item in existing if item.state == "queued")
    replaceable_coords = frozenset(
        item.coord for item in existing if item.state in REPLACEABLE_QUEUE_STATES
    )

    unique: dict[str, QueueTargetFact] = {}
    skipped: list[QueueSkippedFact] = []
    for item in sorted(targets, key=lambda row: (row.coord, str(row.report_id or ""))):
        if item.coord in unique:
            skipped.append(QueueSkippedFact(item.coord, QueueSkipReason.DUPLICATE_INPUT))
            continue
        unique[item.coord] = item

    eligible: list[QueueTargetFact] = []
    for item in unique.values():
        reason = _eligibility_reason(
            item,
            mode,
            now=now,
            active_targets=active,
            minimum_metal=minimum_metal,
            lookback_hours=lookback_hours,
        )
        if reason is not None:
            skipped.append(QueueSkippedFact(item.coord, reason))
            continue
        if item.coord in protected_coords:
            skipped.append(QueueSkippedFact(item.coord, QueueSkipReason.PROTECTED_EXISTING))
            continue
        eligible.append(item)

    eligible.sort(key=lambda item: _rank_key(item, mode))
    selected = eligible[:size]
    for item in eligible[size:]:
        skipped.append(QueueSkippedFact(item.coord, QueueSkipReason.OUTSIDE_LIMIT))

    desired = tuple(
        QueueDesiredRow(
            position=index,
            coord=item.coord,
            player=item.player or "—",
            metal=item.metal,
            minerals=item.minerals,
            gas=item.gas,
            last_spy_at=_as_utc(item.reported_at).replace(microsecond=0).isoformat(),
            enabled=item.enabled,
            blacklisted=item.blacklisted,
        )
        for index, item in enumerate(selected, start=1)
    )
    desired_coords = tuple(item.coord for item in desired)
    desired_set = frozenset(desired_coords)
    kept = tuple(coord for coord in desired_coords if coord in existing_queued)
    added = tuple(coord for coord in desired_coords if coord not in existing_queued)
    removed = tuple(sorted(replaceable_coords - desired_set))
    protected = tuple(sorted(protected_coords))
    skipped.sort(key=lambda item: (item.reason.value, item.coord))
    return QueueRefillPreview(
        mode=mode,
        queue_size=size,
        desired=desired,
        added=added,
        kept=kept,
        removed=removed,
        protected=protected,
        skipped=tuple(skipped),
    )
