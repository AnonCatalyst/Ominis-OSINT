"""Dark palette and stylesheet for the Ominis workstation."""

from __future__ import annotations

BG = "#070d1b"
BG_RAISED = "#0a1326"
PANEL = "#0d1730"
PANEL_ALT = "#101d3b"
LINE = "#223352"
LINE_SOFT = "#17243f"
INK = "#dbe7ff"
MUTED = "#8fa3c8"
GLOW = "#58e1ff"
EMBER = "#ffb45c"
GREEN = "#7ef0b2"
RED = "#ff6b81"
VIOLET = "#b18cff"

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable", "Noto Sans", sans-serif;
    font-size: 10pt;
    outline: 0;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QWidget {{
    color: {INK};
}}
QToolTip {{
    background: {PANEL_ALT};
    color: {INK};
    border: 1px solid {LINE};
    padding: 6px 8px;
    border-radius: 6px;
}}

QMenuBar {{
    background: {BG};
    border-bottom: 1px solid {LINE_SOFT};
    padding: 2px 6px;
}}
QMenuBar::item {{
    padding: 5px 10px;
    border-radius: 6px;
    color: {MUTED};
}}
QMenuBar::item:selected {{ background: {PANEL}; color: {INK}; }}
QMenu {{
    background: {PANEL};
    border: 1px solid {LINE};
    padding: 6px;
}}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {PANEL_ALT}; color: {GLOW}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 6px 8px; }}

QFrame#CommandBar {{
    background: {BG_RAISED};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
QFrame#SidePanel {{
    background: {BG_RAISED};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QFrame#Inspector {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QFrame#Hairline {{ background: {LINE_SOFT}; max-height: 1px; min-height: 1px; }}

QLabel#BrandMark {{
    background: {PANEL_ALT};
    border: 1px solid #2d5a9e;
    border-radius: 11px;
    color: {GLOW};
    font-weight: 700;
    font-size: 13pt;
}}
QLabel#BrandName {{ font-size: 13pt; font-weight: 700; letter-spacing: 0.3px; }}
QLabel#BrandSub {{
    color: {MUTED};
    font-size: 8pt;
    letter-spacing: 1.4px;
    text-transform: uppercase;
}}
QLabel#Eyebrow {{
    color: {EMBER};
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.6px;
    text-transform: uppercase;
}}
QLabel#PageTitle {{ font-size: 17pt; font-weight: 700; }}
QLabel#Hint {{ color: {MUTED}; font-size: 9pt; }}
QLabel#CardLabel {{
    color: {MUTED};
    font-size: 8pt;
    letter-spacing: 1.3px;
    text-transform: uppercase;
}}
QLabel#CardValue {{ font-size: 22pt; font-weight: 700; }}
QLabel#SectionLabel {{
    color: {GLOW};
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.3px;
    text-transform: uppercase;
}}
QLabel#Mono {{
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 9pt;
    color: #bfd4ff;
}}
QLabel#Pill {{
    background: {PANEL_ALT};
    border: 1px solid {LINE};
    border-radius: 9px;
    color: {MUTED};
    font-size: 8pt;
    padding: 2px 8px;
}}
QLabel#PillGood {{
    background: #0f2a22;
    border: 1px solid #1f5b45;
    border-radius: 9px;
    color: {GREEN};
    font-size: 8pt;
    padding: 2px 8px;
}}
QLabel#PillWarn {{
    background: #2a2110;
    border: 1px solid #5a3a1e;
    border-radius: 9px;
    color: {EMBER};
    font-size: 8pt;
    padding: 2px 8px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background: {BG};
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: #1d4b7a;
    min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QDateEdit:focus {{
    border: 1px solid {GLOW};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    color: #5c6c8a;
    background: #0a1120;
}}
QDateEdit:disabled {{ color: #5c6c8a; background: #0a1120; }}
QLineEdit#TargetInput {{
    font-size: 12pt;
    padding: 10px 14px;
    border-radius: 11px;
}}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid {LINE};
    selection-background-color: {PANEL_ALT};
    selection-color: {GLOW};
    padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px; border: 0; background: transparent;
}}

QPushButton {{
    background: {PANEL_ALT};
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 8px 14px;
    color: {INK};
}}
QPushButton:hover {{ border-color: #35609c; background: #14264a; }}
QPushButton:pressed {{ background: #0f1c36; }}
QPushButton:disabled {{ color: #5c6c8a; background: #0a1120; border-color: #16223a; }}
QPushButton#Primary {{
    background: #1c4f8a;
    border: 1px solid #2f78c8;
    color: #eaf6ff;
    font-weight: 700;
    padding: 10px 22px;
}}
QPushButton#Primary:hover {{ background: #2362a8; }}
QPushButton#Primary:disabled {{ background: #14294a; border-color: #223b5e; color: #6d82a4; }}
QPushButton#Danger {{
    background: #2a1420;
    border: 1px solid #5a2436;
    color: {RED};
}}
QPushButton#Danger:hover {{ background: #3a1a2a; }}

QCheckBox {{ spacing: 8px; color: {INK}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {LINE};
    border-radius: 4px;
    background: {BG};
}}
QCheckBox::indicator:checked {{
    background: {GLOW};
    border: 1px solid {GLOW};
}}
QCheckBox::indicator:disabled {{ border-color: #22304d; background: #0a1120; }}

QTabWidget::pane {{
    border: 1px solid {LINE};
    border-radius: 12px;
    background: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 16px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {INK}; }}
QTabBar::tab:selected {{
    color: {GLOW};
    background: {PANEL};
    border: 1px solid {LINE};
    border-bottom-color: {PANEL};
}}

QTableView, QTableWidget {{
    background: {PANEL};
    alternate-background-color: #0b1428;
    border: 0;
    gridline-color: {LINE_SOFT};
    selection-background-color: #14304f;
    selection-color: {INK};
}}
QTableView::item, QTableWidget::item {{ padding: 7px 8px; border: 0; }}
QHeaderView::section {{
    background: {BG_RAISED};
    color: {MUTED};
    border: 0;
    border-bottom: 1px solid {LINE};
    padding: 8px;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QTableCornerButton::section {{ background: {BG_RAISED}; border: 0; }}

QListWidget {{
    background: {PANEL};
    border: 0;
}}
QListWidget::item {{
    background: {BG_RAISED};
    border: 1px solid {LINE_SOFT};
    border-radius: 9px;
    padding: 9px 11px;
    margin: 3px 2px;
}}
QListWidget::item:selected {{
    border-color: {GLOW};
    background: #122944;
}}

QPlainTextEdit {{
    background: #050b16;
    border: 0;
    color: #c9d8f5;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 9pt;
    padding: 10px;
    selection-background-color: #1d4b7a;
}}

QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#InspectorBody {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #24395e; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #33527f; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #24395e; border-radius: 5px; min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{ background: transparent; width: 8px; }}
QSplitter::handle:hover {{ background: {LINE_SOFT}; }}

QStatusBar {{
    background: {BG};
    border-top: 1px solid {LINE_SOFT};
    color: {MUTED};
}}
QStatusBar::item {{ border: 0; }}
QProgressBar {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {GLOW};
    border-radius: 5px;
}}

QDialog#Sheet {{ background: {BG}; }}
QGroupBox {{
    border: 1px solid {LINE};
    border-radius: 11px;
    margin-top: 16px;
    padding: 14px 12px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {GLOW};
}}
"""
