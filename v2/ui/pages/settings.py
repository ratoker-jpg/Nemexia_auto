from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from v2.application.context import V2ApplicationContext


class SettingsPage(QWidget):
    """Edit only allow-listed settings in the isolated V2 database."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        card = QFrame(self)
        card.setObjectName("InfoCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        title = QLabel("Параметры V2", card)
        title.setObjectName("SectionTitle")
        card_layout.addWidget(title)
        note = QLabel(
            "Сохраняются только в изолированной V2 SQLite. Рабочая legacy-база остаётся только для чтения.",
            card,
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        card_layout.addWidget(note)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        self.cdp_port = QSpinBox(card)
        self.cdp_port.setRange(1, 65535)
        form.addRow("CDP port", self.cdp_port)

        self.farm_home = QLineEdit(card)
        self.farm_home.setPlaceholderText("3:39:11")
        form.addRow("Планета автофарма", self.farm_home)

        self.command_planet = QLineEdit(card)
        self.command_planet.setPlaceholderText("2:5:6")
        form.addRow("Командная планета", self.command_planet)

        self.return_buffer = QSpinBox(card)
        self.return_buffer.setRange(0, 60)
        self.return_buffer.setSuffix(" мин")
        form.addRow("Буфер после возврата", self.return_buffer)

        card_layout.addLayout(form)

        self.save_button = QPushButton("Сохранить", card)
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_settings)
        card_layout.addWidget(self.save_button)

        self.status_label = QLabel("", card)
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)
        layout.addWidget(card)
        layout.addStretch(1)

        self.reload_view()

    def reload_view(self) -> None:
        if not self.context.v2_settings_available():
            self.save_button.setEnabled(False)
            self.status_label.setText("V2 settings storage недоступен.")
            return
        values = self.context.v2_settings_snapshot()
        self.cdp_port.setValue(int(values["cdp_port"]))
        self.farm_home.setText(str(values["farm_home"]))
        self.command_planet.setText(str(values["command_planet"]))
        self.return_buffer.setValue(int(values["farm_return_buffer_minutes"]))
        self.save_button.setEnabled(True)
        if not self.status_label.text():
            self.status_label.setText("Настройки загружены из V2 SQLite.")

    def save_settings(self) -> None:
        self.save_button.setEnabled(False)
        try:
            self.context.set_v2_setting("cdp_port", self.cdp_port.value())
            self.context.set_v2_setting("farm_home", self.farm_home.text())
            self.context.set_v2_setting("command_planet", self.command_planet.text())
            self.context.set_v2_setting(
                "farm_return_buffer_minutes", self.return_buffer.value()
            )
        except Exception as exc:
            self.status_label.setText(f"Не сохранено: {exc}")
        else:
            self.reload_view()
            self.status_label.setText(
                "Сохранено в V2. CDP port применяется после перезапуска app_qt.py; "
                "планеты и буфер используются новым V2 policy сразу."
            )
        finally:
            self.save_button.setEnabled(self.context.v2_settings_available())
