from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from v2.application.context import V2ApplicationContext


def _display(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


class ReadOnlyRowsModel(QAbstractTableModel):
    def __init__(self, headers: Sequence[str], rows: Sequence[Sequence[object]], parent=None) -> None:
        super().__init__(parent)
        self.headers = tuple(headers)
        self.rows = tuple(tuple(row) for row in rows)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return _display(self.rows[index.row()][index.column()])

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return section + 1

    def replace_rows(self, rows: Sequence[Sequence[object]]) -> None:
        """Replace displayed facts without enabling any editing path."""
        self.beginResetModel()
        self.rows = tuple(tuple(row) for row in rows)
        self.endResetModel()


class FilterableReadOnlyTable(QWidget):
    def __init__(self, headers: Sequence[str], rows: Sequence[Sequence[object]], *, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        search = QLineEdit(self)
        search.setObjectName("TableSearch")
        search.setPlaceholderText(placeholder)
        search.setClearButtonEnabled(True)
        layout.addWidget(search)

        card = QFrame(self)
        card.setObjectName("DataCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(1, 1, 1, 1)

        self.model = ReadOnlyRowsModel(headers, rows, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        search.textChanged.connect(self.proxy.setFilterFixedString)

        table = QTableView(card)
        table.setObjectName("DataTable")
        table.setModel(self.proxy)
        table.setSortingEnabled(True)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setMinimumSectionSize(76)
        card_layout.addWidget(table)
        layout.addWidget(card, 1)
        self.table = table


class TargetsPage(FilterableReadOnlyTable):
    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        targets = context.targets()
        rows = [
            (
                item.coord,
                item.player,
                item.energy,
                item.metal,
                item.minerals,
                item.gas,
                item.last_spy_at,
                item.raid_count,
                "Blacklist" if item.blacklisted else ("Включена" if item.enabled else "Выключена"),
            )
            for item in targets
        ]
        super().__init__(
            ("Координаты", "Игрок", "Энергия", "Металл", "Минералы", "Газ", "Разведка", "Рейдов", "Состояние"),
            rows,
            placeholder="Поиск по координатам, игроку, ресурсам или состоянию…",
            parent=parent,
        )


class HistoryPage(FilterableReadOnlyTable):
    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        history = context.history()
        rows = [
            (
                item.sent_at,
                item.source,
                item.target,
                item.player,
                item.ship_count,
                item.return_at,
                item.status,
                item.error,
            )
            for item in history
        ]
        super().__init__(
            ("Отправлен", "Откуда", "Цель", "Игрок", "Кораблей", "Возврат", "Статус", "Ошибка"),
            rows,
            placeholder="Поиск по истории отправок…",
            parent=parent,
        )
