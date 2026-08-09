from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from v2.ui.theme import SPACING


def _refresh_style(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def set_tone(widget: QWidget, tone: str) -> None:
    widget.setProperty("tone", tone)
    _refresh_style(widget)


def command_button(
    text: str,
    *,
    tone: str = "secondary",
    compact: bool = False,
    parent: QWidget | None = None,
) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName("CommandButton")
    button.setProperty("tone", tone)
    button.setProperty("compact", "true" if compact else "false")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class StatusPill(QLabel):
    def __init__(self, text: str, tone: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusPill")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_status(self, text: str, tone: str = "neutral") -> None:
        self.setText(text)
        set_tone(self, tone)


class MetricCard(QFrame):
    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        *,
        tone: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["xs"])
        self.label = QLabel(label, self)
        self.label.setObjectName("MetricLabel")
        self.value = QLabel(value, self)
        self.value.setObjectName("MetricValue")
        self.hint = QLabel(hint, self)
        self.hint.setObjectName("MetricHint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_value(self, value: str, hint: str | None = None, tone: str | None = None) -> None:
        self.value.setText(value)
        if hint is not None:
            self.hint.setText(hint)
        if tone is not None:
            set_tone(self, tone)


class StateBanner(QFrame):
    def __init__(
        self,
        title: str,
        detail: str = "",
        *,
        tone: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StateBanner")
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])
        layout.setSpacing(SPACING["xs"])
        self.title = QLabel(title, self)
        self.title.setObjectName("SectionTitle")
        self.detail = QLabel(detail, self)
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)

    def set_state(self, title: str, detail: str, tone: str = "info") -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        set_tone(self, tone)


class SectionCard(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        object_name: str = "SectionCard",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        outer.setSpacing(SPACING["md"])
        header = QVBoxLayout()
        header.setSpacing(SPACING["xs"])
        heading = QLabel(title, self)
        heading.setObjectName("SectionTitle")
        header.addWidget(heading)
        if subtitle:
            description = QLabel(subtitle, self)
            description.setObjectName("CardSubtitle")
            description.setWordWrap(True)
            header.addWidget(description)
        outer.addLayout(header)
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(SPACING["md"])
        outer.addLayout(self.content_layout)


class EmptyState(QFrame):
    def __init__(self, title: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StateBanner")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["xs"])
        heading = QLabel(title, self)
        heading.setObjectName("SectionTitle")
        body = QLabel(detail, self)
        body.setObjectName("Muted")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)


def page_layout(widget: QWidget, *, spacing: int | None = None) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
    layout.setSpacing(SPACING["lg"] if spacing is None else spacing)
    return layout


def scrollable_page(parent: QWidget) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea(parent)
    scroll.setObjectName("PageScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget(scroll)
    content.setObjectName("PageScrollContent")
    layout = page_layout(content)
    scroll.setWidget(content)
    return scroll, content, layout


def toolbar(parent: QWidget | None = None) -> tuple[QFrame, QHBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("CommandToolbar")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACING["sm"])
    return frame, layout
