from __future__ import annotations


COLORS = {
    "bg_base": "#080D14",
    "bg_sidebar": "#0B121C",
    "surface_1": "#101925",
    "surface_2": "#152232",
    "surface_3": "#1B2B3E",
    "border_subtle": "#213247",
    "border_strong": "#304765",
    "text_primary": "#F2F6FC",
    "text_secondary": "#A7B5C8",
    "text_muted": "#68798F",
    "accent_blue": "#5B8CFF",
    "accent_cyan": "#2DC8D3",
    "success": "#3BD18A",
    "warning": "#FFB454",
    "danger": "#FF6270",
}


ORBITAL_COMMAND_QSS = f"""
QWidget {{
    background: {COLORS['bg_base']};
    color: {COLORS['text_primary']};
    font-family: 'Segoe UI';
    font-size: 13px;
}}
QFrame#Sidebar {{
    background: {COLORS['bg_sidebar']};
    border-right: 1px solid {COLORS['border_subtle']};
}}
QLabel#Brand {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel#BrandAccent {{
    color: {COLORS['accent_blue']};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#SectionLabel {{
    color: {COLORS['text_muted']};
    font-size: 10px;
    font-weight: 600;
}}
QPushButton#NavButton {{
    text-align: left;
    padding: 9px 12px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: {COLORS['text_secondary']};
}}
QPushButton#NavButton:hover {{
    background: {COLORS['surface_2']};
    color: {COLORS['text_primary']};
}}
QPushButton#NavButton:checked {{
    background: {COLORS['surface_3']};
    color: {COLORS['text_primary']};
    border-left: 3px solid {COLORS['accent_blue']};
}}
QFrame#Topbar {{
    background: {COLORS['bg_base']};
    border-bottom: 1px solid {COLORS['border_subtle']};
}}
QLabel#PageTitle {{
    font-size: 26px;
    font-weight: 600;
}}
QLabel#PageDescription {{
    color: {COLORS['text_secondary']};
}}
QLabel#StatusBadge {{
    background: {COLORS['surface_2']};
    color: {COLORS['success']};
    border: 1px solid {COLORS['border_subtle']};
    border-radius: 8px;
    padding: 6px 10px;
}}
QFrame#PlaceholderCard {{
    background: {COLORS['surface_1']};
    border: 1px solid {COLORS['border_subtle']};
    border-radius: 12px;
}}
QLabel#PlaceholderTitle {{
    font-size: 16px;
    font-weight: 600;
}}
QLabel#Muted {{
    color: {COLORS['text_muted']};
}}
"""
