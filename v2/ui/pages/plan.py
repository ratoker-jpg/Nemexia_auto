from __future__ import annotations

from v2.application.context import V2ApplicationContext
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class PlanPage(FilterableReadOnlyTable):
    """Read-only view of the queue persisted by the legacy application."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        items = context.plan()
        rows = [
            (
                item.position,
                item.coord,
                item.player,
                item.metal,
                item.minerals,
                item.gas,
                item.last_spy_at,
                item.state,
                "Blacklist" if item.blacklisted else ("Включена" if item.enabled else "Выключена"),
            )
            for item in items
        ]
        super().__init__(
            ("#", "Координаты", "Игрок", "Металл", "Минералы", "Газ", "Разведка", "Состояние очереди", "Цель"),
            rows,
            placeholder="Поиск по сохранённому плану…",
            parent=parent,
        )
