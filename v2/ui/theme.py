from __future__ import annotations

COLORS = {
    "bg_base": "#080D14", "bg_sidebar": "#0B121C",
    "surface_1": "#101925", "surface_2": "#152232", "surface_3": "#1B2B3E",
    "border_subtle": "#213247", "border_strong": "#304765",
    "text_primary": "#F2F6FC", "text_secondary": "#A7B5C8", "text_muted": "#76889F",
    "accent_blue": "#5B8CFF", "accent_hover": "#7AA4FF", "accent_cyan": "#2DC8D3",
    "success": "#3BD18A", "warning": "#FFB454", "danger": "#FF6270",
}
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADII = {"sm": 6, "md": 8, "lg": 12}
SIZES = {"sidebar": 220, "topbar": 80, "button_regular": 38, "button_compact": 32, "input": 38, "table_row": 40}
TYPOGRAPHY = {
    "display": (28, 700), "page_title": (26, 600), "section_title": (16, 600),
    "metric": (26, 700), "body_strong": (13, 600), "body": (13, 400),
    "caption": (11, 600), "mono": (12, 400),
}

ORBITAL_COMMAND_QSS = f"""
QWidget {{ background:{COLORS['bg_base']}; color:{COLORS['text_primary']}; font-family:'Segoe UI'; font-size:13px; }}
QToolTip {{ background:{COLORS['surface_2']}; color:{COLORS['text_primary']}; border:1px solid {COLORS['border_strong']}; padding:6px 8px; }}
QFrame#Sidebar {{ background:{COLORS['bg_sidebar']}; border-right:1px solid {COLORS['border_subtle']}; }}
QLabel#Brand {{ font-size:19px; font-weight:700; }}
QLabel#BrandAccent {{ color:{COLORS['accent_blue']}; font-size:11px; font-weight:600; }}
QLabel#SectionLabel {{ color:{COLORS['text_muted']}; font-size:10px; font-weight:600; padding:4px 10px 2px 10px; }}
QLabel#SidebarMeta, QLabel#Muted, QLabel#MetricHint {{ color:{COLORS['text_muted']}; }}
QPushButton#NavButton {{ min-height:34px; text-align:left; padding:0 12px; border:0; border-left:3px solid transparent; border-radius:8px; background:transparent; color:{COLORS['text_secondary']}; }}
QPushButton#NavButton:hover {{ background:{COLORS['surface_2']}; color:{COLORS['text_primary']}; }}
QPushButton#NavButton:checked {{ background:{COLORS['surface_3']}; color:{COLORS['text_primary']}; border-left:3px solid {COLORS['accent_blue']}; font-weight:600; }}
QFrame#Topbar {{ background:{COLORS['bg_base']}; border-bottom:1px solid {COLORS['border_subtle']}; }}
QFrame#BrowserReadinessBar {{ background:{COLORS['bg_sidebar']}; border-bottom:1px solid {COLORS['border_subtle']}; }}
QLabel#PageTitle {{ font-size:26px; font-weight:600; }}
QLabel#PageDescription, QLabel#CardSubtitle, QLabel#PageHint {{ color:{COLORS['text_secondary']}; font-size:12px; }}
QLabel#StatusBadge, QLabel#StatusPill {{ background:{COLORS['surface_2']}; color:{COLORS['text_secondary']}; border:1px solid {COLORS['border_subtle']}; border-radius:8px; padding:5px 9px; font-size:11px; font-weight:600; }}
QLabel#StatusPill[tone="success"], QLabel#StatusBadge[tone="success"] {{ color:{COLORS['success']}; }}
QLabel#StatusPill[tone="warning"], QLabel#StatusBadge[tone="warning"] {{ color:{COLORS['warning']}; }}
QLabel#StatusPill[tone="danger"], QLabel#StatusBadge[tone="danger"] {{ color:{COLORS['danger']}; }}
QLabel#StatusPill[tone="info"], QLabel#StatusBadge[tone="info"] {{ color:{COLORS['accent_cyan']}; }}
QFrame#PlaceholderCard, QFrame#DataCard, QFrame#InfoCard, QFrame#MetricCard, QFrame#SectionCard, QFrame#CommandCard, QFrame#DefinitionCard {{ background:{COLORS['surface_1']}; border:1px solid {COLORS['border_subtle']}; border-radius:12px; }}
QFrame#MetricCard[tone="info"] {{ border-top:2px solid {COLORS['accent_blue']}; }}
QFrame#MetricCard[tone="success"] {{ border-top:2px solid {COLORS['success']}; }}
QFrame#MetricCard[tone="warning"] {{ border-top:2px solid {COLORS['warning']}; }}
QFrame#MetricCard[tone="danger"] {{ border-top:2px solid {COLORS['danger']}; }}
QFrame#StateBanner {{ background:{COLORS['surface_1']}; border:1px solid {COLORS['border_subtle']}; border-left:3px solid {COLORS['accent_blue']}; border-radius:8px; }}
QFrame#StateBanner[tone="success"] {{ border-left-color:{COLORS['success']}; }}
QFrame#StateBanner[tone="warning"] {{ border-left-color:{COLORS['warning']}; }}
QFrame#StateBanner[tone="danger"] {{ border-left-color:{COLORS['danger']}; }}
QLabel#PlaceholderTitle, QLabel#SectionTitle {{ font-size:16px; font-weight:600; }}
QLabel#MetricLabel {{ color:{COLORS['text_secondary']}; font-size:11px; font-weight:600; }}
QLabel#MetricValue {{ font-size:26px; font-weight:700; }}
QLabel#Mono {{ color:{COLORS['text_secondary']}; font-family:'Consolas'; font-size:12px; }}
QPushButton {{ min-height:38px; padding:0 14px; background:{COLORS['surface_2']}; color:{COLORS['text_primary']}; border:1px solid {COLORS['border_strong']}; border-radius:8px; font-weight:600; }}
QPushButton:hover {{ background:{COLORS['surface_3']}; }}
QPushButton:focus {{ border:2px solid {COLORS['accent_blue']}; }}
QPushButton:disabled {{ background:{COLORS['surface_1']}; color:{COLORS['text_muted']}; border-color:{COLORS['border_subtle']}; }}
QPushButton[compact="true"] {{ min-height:32px; padding:0 10px; }}
QPushButton#PrimaryButton, QPushButton[tone="primary"] {{ background:{COLORS['accent_blue']}; border-color:{COLORS['accent_blue']}; color:#FFFFFF; }}
QPushButton#SecondaryButton, QPushButton[tone="secondary"] {{ background:{COLORS['surface_2']}; }}
QPushButton[tone="warning"] {{ background:#3A2B16; color:{COLORS['warning']}; border-color:#73552B; }}
QPushButton[tone="danger"] {{ background:#351A21; color:{COLORS['danger']}; border-color:#6B3340; }}
QPushButton[tone="ghost"] {{ background:transparent; border-color:transparent; color:{COLORS['text_secondary']}; }}
QLineEdit, QSpinBox, QComboBox {{ min-height:38px; padding:0 10px; background:{COLORS['surface_2']}; color:{COLORS['text_primary']}; border:1px solid {COLORS['border_subtle']}; border-radius:8px; selection-background-color:{COLORS['accent_blue']}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border:2px solid {COLORS['accent_blue']}; }}
QLineEdit#TableSearch {{ background:{COLORS['surface_1']}; }}
QCheckBox {{ spacing:8px; }}
QTableView#DataTable {{ background:{COLORS['surface_1']}; border:0; gridline-color:{COLORS['border_subtle']}; selection-background-color:{COLORS['surface_3']}; selection-color:{COLORS['text_primary']}; }}
QTableView#DataTable::item {{ padding:7px 9px; border-bottom:1px solid {COLORS['border_subtle']}; }}
QHeaderView::section {{ background:{COLORS['surface_2']}; color:{COLORS['text_secondary']}; border:0; border-right:1px solid {COLORS['border_subtle']}; border-bottom:1px solid {COLORS['border_strong']}; padding:9px 8px; font-weight:600; }}
QScrollArea {{ border:0; background:transparent; }}
QScrollBar:vertical {{ background:{COLORS['bg_base']}; width:10px; }}
QScrollBar:horizontal {{ background:{COLORS['bg_base']}; height:10px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background:{COLORS['border_strong']}; border-radius:5px; min-width:28px; min-height:28px; }}
QMessageBox {{ background:{COLORS['surface_1']}; }}
QMessageBox QLabel {{ background:transparent; color:{COLORS['text_primary']}; min-width:280px; }}
"""
