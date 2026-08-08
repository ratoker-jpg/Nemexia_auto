from __future__ import annotations

from v2.application.context import V2ApplicationContext
from v2.ui.pages.read_tables import FilterableReadOnlyTable


class ReconPage(FilterableReadOnlyTable):
    """Display only spy reports already persisted by the working legacy app."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        reports = context.recon()
        rows = [
            (
                item.report_at,
                item.target_coord,
                item.energy,
                item.metal,
                item.minerals,
                item.gas,
                item.population,
                item.ships,
                item.defense,
                item.completeness,
                item.source,
            )
            for item in reports
        ]
        super().__init__(
            (
                "Отчёт", "Координаты", "Энергия", "Металл", "Минералы", "Газ",
                "Население", "Корабли", "Защита", "Полнота", "Источник",
            ),
            rows,
            placeholder="Поиск по сохранённой разведке…",
            parent=parent,
        )
