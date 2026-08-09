from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLineEdit,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from v2.application.context import V2ApplicationContext
from v2.ui.components import EmptyState, StateBanner
from v2.ui.theme import SIZES, SPACING


def _display(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return str(value)


def _column_alignment(header: str, value: object) -> Qt.AlignmentFlag:
    numeric_headers = {"Энергия", "Металл", "Минералы", "Газ", "Кораблей", "#"}
    centered_headers = {
        "Координаты", "Откуда", "Куда", "Цель", "Разведка", "Возврат", "Отправлен",
        "Fleet ID", "Report ID", "Состояние", "Состояние очереди", "Направление",
        "Scope", "В расчётах", "Таймер фарма",
    }
    if header in numeric_headers or isinstance(value, int):
        return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    if header in centered_headers:
        return Qt.AlignmentFlag.AlignCenter
    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


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
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return _display(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _column_alignment(self.headers[index.column()], value)
        return None

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
    def __init__(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        *,
        placeholder: str,
        intro_title: str = "",
        intro_detail: str = "",
        empty_title: str = "Нет данных",
        empty_detail: str = "Нет строк для отображения в текущем V2-owned источнике.",
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        layout.setSpacing(SPACING["md"])

        if intro_title:
            intro = StateBanner(intro_title, intro_detail, tone="info", parent=self)
            layout.addWidget(intro)

        search = QLineEdit(self)
        search.setObjectName("TableSearch")
        search.setPlaceholderText(placeholder)
        search.setClearButtonEnabled(True)
        layout.addWidget(search)

        card = QFrame(self)
        card.setObjectName("DataCard")
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
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
        table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        table.setModel(self.proxy)
        table.setSortingEnabled(True)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(SIZES["table_row"])
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setMinimumSectionSize(76)
        card_layout.addWidget(table)
        layout.addWidget(card, 1)

        self.empty_state = EmptyState(empty_title, empty_detail, self)
        layout.addWidget(self.empty_state)
        self.table_card = card
        self.table = table
        self.model.modelReset.connect(self._sync_empty_state)
        self._sync_empty_state()

    def _sync_empty_state(self) -> None:
        empty = self.model.rowCount() == 0
        self.empty_state.setVisible(empty)
        self.table_card.setVisible(not empty)


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
                item.latest_report_id,
                "Blacklist" if item.blacklisted else ("Включена" if item.enabled else "Выключена"),
            )
            for item in targets
        ]
        super().__init__(
            (
                "Координаты", "Игрок", "Энергия", "Металл", "Минералы", "Газ",
                "Разведка", "Report ID", "Состояние",
            ),
            rows,
            placeholder="Поиск по V2-целям, ресурсам или состоянию…",
            intro_title="V2-owned цели",
            intro_detail="Read-only рабочий список в этом UI batch: поиск и сортировка не изменяют target state.",
            empty_title="Цели пока отсутствуют",
            empty_detail="V2-owned targets не содержат строк. CRUD и browser discovery в этом visual batch не добавляются.",
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
            intro_title="История подтверждённых и остановленных операций",
            intro_detail="Сохранённые факты V2/legacy read boundary. Экран не запускает действий и не исправляет историю автоматически.",
            empty_title="История пока пуста",
            empty_detail="Нет сохранённых строк отправок для отображения.",
            parent=parent,
        )
