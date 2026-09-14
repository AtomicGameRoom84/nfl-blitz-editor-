"""Dark theme for the suite.

A single palette dictionary plus one stylesheet, so colours used by
custom-painted widgets (the hex view) and by Qt widgets stay in step.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

#: Named colours.  Keep every colour used anywhere in the UI here.
COLORS = {
    "background": "#15181d",
    "surface": "#1c2027",
    "surface_alt": "#232833",
    "surface_raised": "#2a303c",
    "border": "#333b48",
    "text": "#e4e8ef",
    "text_dim": "#97a1b2",
    "text_faint": "#66707f",
    "accent": "#e8a33d",        # warm cartridge amber
    "accent_dark": "#b87d24",
    "accent_text": "#1a1a1a",
    "info": "#5aa9e6",
    "success": "#63c187",
    "warning": "#e6b45a",
    "danger": "#e06c75",
    "modified": "#e8a33d",
    "bookmark": "#9d7ce8",
    "match": "#5aa9e6",
    "selection": "#39465c",
}


def color(name: str) -> QColor:
    """Look up a palette colour as a :class:`QColor`."""
    return QColor(COLORS[name])


def monospace_font(point_size: int = 12) -> QFont:
    """A fixed-pitch font that exists on every platform Qt runs on."""
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(point_size)
    font.setStyleHint(QFont.Monospace)
    font.setFixedPitch(True)
    return font


STYLESHEET = f"""
/* No background here: plain container widgets stay transparent so a layout
   helper placed inside a card does not paint the window colour over it.
   Surfaces are set explicitly on the widgets that need one. */
QWidget {{
    color: {COLORS['text']};
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {COLORS['background']};
}}

/* A scrolled page still needs a ground to paint on. */
QScrollArea#PageScroll, QWidget#PageScrollBody {{
    background-color: {COLORS['background']};
}}

/* Labels and check boxes must not paint the window colour over a card. */
QLabel, QCheckBox, QRadioButton, QGroupBox::title {{
    background: transparent;
}}

/* ---- sidebar ---- */
QListWidget#Sidebar {{
    background-color: {COLORS['surface']};
    border: none;
    border-right: 1px solid {COLORS['border']};
    outline: none;
    padding: 6px 0;
}}
QListWidget#Sidebar::item {{
    padding: 9px 16px;
    margin: 1px 6px;
    border-radius: 5px;
    color: {COLORS['text_dim']};
}}
QListWidget#Sidebar::item:selected {{
    background-color: {COLORS['surface_raised']};
    color: {COLORS['accent']};
    font-weight: bold;
}}
QListWidget#Sidebar::item:hover:!selected {{
    background-color: {COLORS['surface_alt']};
    color: {COLORS['text']};
}}
QListWidget#Sidebar::item:disabled {{
    color: {COLORS['text_faint']};
}}

/* ---- headings ---- */
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: bold;
    color: {COLORS['text']};
}}
QLabel#PageSubtitle {{
    color: {COLORS['text_dim']};
}}
QLabel#SectionHeading {{
    font-weight: bold;
    color: {COLORS['accent']};
    padding-top: 4px;
}}
QLabel#SidebarHeading {{
    color: {COLORS['text_faint']};
    font-size: 11px;
    font-weight: bold;
    padding: 10px 16px 2px 16px;
}}
QLabel#Hint {{
    color: {COLORS['text_dim']};
}}

/* ---- panels ---- */
QFrame#Card {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}
QGroupBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px;
    background-color: {COLORS['surface']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {COLORS['accent']};
    font-weight: bold;
}}

/* ---- inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 5px 7px;
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['accent_text']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {COLORS['accent']};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QPlainTextEdit:disabled {{
    color: {COLORS['text_faint']};
    background-color: {COLORS['surface']};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['surface_raised']};
}}

/* ---- buttons ---- */
QPushButton {{
    background-color: {COLORS['surface_raised']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background-color: {COLORS['border']}; }}
QPushButton:pressed {{ background-color: {COLORS['surface_alt']}; }}
QPushButton:disabled {{ color: {COLORS['text_faint']}; background-color: {COLORS['surface']}; }}
QPushButton#Primary {{
    background-color: {COLORS['accent']};
    color: {COLORS['accent_text']};
    border: 1px solid {COLORS['accent_dark']};
    font-weight: bold;
}}
QPushButton#Primary:hover {{ background-color: {COLORS['accent_dark']}; }}
QPushButton#Primary:disabled {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_faint']};
    border: 1px solid {COLORS['border']};
}}

/* ---- tables ---- */
QTableView, QTreeView, QListView {{
    background-color: {COLORS['surface']};
    alternate-background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    gridline-color: {COLORS['border']};
    selection-background-color: {COLORS['selection']};
    selection-color: {COLORS['text']};
}}
QHeaderView::section {{
    background-color: {COLORS['surface_raised']};
    color: {COLORS['text_dim']};
    border: none;
    border-right: 1px solid {COLORS['border']};
    border-bottom: 1px solid {COLORS['border']};
    padding: 5px 8px;
    font-weight: bold;
}}
QTableView::item:selected {{ background-color: {COLORS['selection']}; }}

/* ---- misc ---- */
QMenuBar {{ background-color: {COLORS['surface']}; border-bottom: 1px solid {COLORS['border']}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {COLORS['surface_raised']}; }}
QMenu {{ background-color: {COLORS['surface_alt']}; border: 1px solid {COLORS['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 26px 6px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {COLORS['surface_raised']}; color: {COLORS['accent']}; }}
QMenu::separator {{ height: 1px; background: {COLORS['border']}; margin: 4px 8px; }}

QStatusBar {{ background-color: {COLORS['surface']}; border-top: 1px solid {COLORS['border']}; color: {COLORS['text_dim']}; }}
QStatusBar::item {{ border: none; }}

QToolBar {{ background-color: {COLORS['surface']}; border-bottom: 1px solid {COLORS['border']}; spacing: 4px; padding: 4px; }}

QScrollBar:vertical {{ background: {COLORS['background']}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {COLORS['border']}; border-radius: 6px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {COLORS['surface_raised']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {COLORS['background']}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {COLORS['border']}; border-radius: 6px; min-width: 30px; }}

QTabWidget::pane {{ border: 1px solid {COLORS['border']}; border-radius: 4px; top: -1px; }}
QTabBar::tab {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: {COLORS['text_dim']};
}}
QTabBar::tab:selected {{ background: {COLORS['surface_raised']}; color: {COLORS['accent']}; }}

QSlider::groove:horizontal {{ height: 5px; background: {COLORS['surface_alt']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {COLORS['accent_dark']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {COLORS['accent']};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:disabled {{ background: {COLORS['border']}; }}

QProgressBar {{
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    background: {COLORS['surface_alt']};
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {COLORS['accent_dark']}; border-radius: 3px; }}

QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator:unchecked {{
    border: 1px solid {COLORS['border']};
    background: {COLORS['surface_alt']};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    border: 1px solid {COLORS['accent_dark']};
    background: {COLORS['accent']};
    border-radius: 3px;
}}
QRadioButton::indicator:unchecked {{
    border: 1px solid {COLORS['border']};
    background: {COLORS['surface_alt']};
    border-radius: 8px;
}}
QRadioButton::indicator:checked {{
    border: 4px solid {COLORS['accent']};
    background: {COLORS['surface_alt']};
    border-radius: 8px;
}}

QSplitter::handle {{ background: {COLORS['border']}; }}
QToolTip {{
    background-color: {COLORS['surface_raised']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    padding: 4px;
}}
"""


def apply_theme(app) -> None:
    """Apply the dark stylesheet to a ``QApplication``."""
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
