from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from v2.application.context import V2ApplicationContext
from v2.ui.components import SectionCard, StateBanner, command_button, scrollable_page
from v2.ui.theme import SPACING


class SettingsPage(QWidget):
    """Edit only allow-listed settings in the isolated V2 database."""

    def __init__(self, context: V2ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll, _content, layout = scrollable_page(self)
        outer.addWidget(scroll)

        isolation = StateBanner(
            "V2-owned settings only",
            "Сохраняются только в изолированной V2 SQLite. Рабочая legacy-база остаётся только для чтения.",
            tone="info",
            parent=self,
        )
        layout.addWidget(isolation)

        connection = SectionCard(
            "Connection",
            "CDP endpoint применяется только к opt-in app_qt.py и не запускает браузер автоматически.",
            parent=self,
        )
        form = QFormLayout()
        form.setHorizontalSpacing(SPACING["lg"])
        form.setVerticalSpacing(SPACING["sm"])
        self.cdp_port = QSpinBox(connection)
        self.cdp_port.setRange(1, 65535)
        form.addRow("CDP port", self.cdp_port)
        connection.content_layout.addLayout(form)
        layout.addWidget(connection)

        account = SectionCard(
            "Account context",
            "Координаты используются существующими V2 application contracts; UI не переключает планеты и вкладки.",
            parent=self,
        )
        account_form = QFormLayout()
        account_form.setHorizontalSpacing(SPACING["lg"])
        account_form.setVerticalSpacing(SPACING["sm"])
        self.farm_home = QLineEdit(account)
        self.farm_home.setPlaceholderText("3:39:11")
        account_form.addRow("Планета автофарма", self.farm_home)
        self.command_planet = QLineEdit(account)
        self.command_planet.setPlaceholderText("2:5:6")
        account_form.addRow("Командная планета", self.command_planet)
        account.content_layout.addLayout(account_form)
        layout.addWidget(account)

        timing = SectionCard(
            "Farm timing",
            "Буфер применяется к существующему typed farm readiness contract.",
            parent=self,
        )
        timing_form = QFormLayout()
        timing_form.setHorizontalSpacing(SPACING["lg"])
        timing_form.setVerticalSpacing(SPACING["sm"])
        self.return_buffer = QSpinBox(timing)
        self.return_buffer.setRange(0, 60)
        self.return_buffer.setSuffix(" мин")
        timing_form.addRow("Буфер после возврата", self.return_buffer)
        timing.content_layout.addLayout(timing_form)
        layout.addWidget(timing)

        safety = SectionCard(
            "Safety gate",
            "actions_enabled разрешает только уже существующие V2 mutation contracts; новые маршруты этим переключателем не создаются.",
            object_name="CommandCard",
            parent=self,
        )
        self.actions_enabled = QCheckBox("Разрешить действия V2", safety)
        self.actions_enabled.setToolTip(
            "По умолчанию выключено. Разрешает только уже реализованные и подтверждаемые V2 action boundaries."
        )
        safety.content_layout.addWidget(self.actions_enabled)
        warning = StateBanner(
            "⚠ Игровые действия",
            "Включай действия только когда открыт нужный аккаунт и требуемая страница. CAPTCHA всегда останавливает V2. "
            "Browser navigation остаётся запрещённой отдельным NO NAVIGATION BOUNDARY.",
            tone="warning",
            parent=safety,
        )
        safety.content_layout.addWidget(warning)
        layout.addWidget(safety)

        save_card = SectionCard("Применение", "Изменения записываются одной allow-listed V2 settings операцией.", parent=self)
        row = QHBoxLayout()
        self.save_button = command_button("Сохранить", tone="primary", parent=save_card)
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_settings)
        row.addWidget(self.save_button)
        row.addStretch(1)
        save_card.content_layout.addLayout(row)
        self.status_label = QLabel("", save_card)
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        save_card.content_layout.addWidget(self.status_label)
        layout.addWidget(save_card)
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
        self.actions_enabled.setChecked(bool(values["actions_enabled"]))
        self.save_button.setEnabled(True)
        if not self.status_label.text():
            state = "разрешены" if self.context.raid_actions_enabled() else "выключены"
            self.status_label.setText(f"Настройки загружены из V2 SQLite · действия {state}.")

    def save_settings(self) -> None:
        self.save_button.setEnabled(False)
        values = {
            "cdp_port": self.cdp_port.value(),
            "farm_home": self.farm_home.text(),
            "command_planet": self.command_planet.text(),
            "farm_return_buffer_minutes": self.return_buffer.value(),
            "actions_enabled": self.actions_enabled.isChecked(),
        }
        try:
            self.context.set_v2_settings(values)
        except Exception as exc:
            self.status_label.setText(f"Не сохранено: {exc}")
        else:
            self.reload_view()
            action_state = "разрешены" if self.context.raid_actions_enabled() else "выключены"
            self.status_label.setText(
                "Сохранено в V2. CDP port применяется после перезапуска app_qt.py; "
                f"действия V2 сейчас {action_state}."
            )
        finally:
            self.save_button.setEnabled(self.context.v2_settings_available())
