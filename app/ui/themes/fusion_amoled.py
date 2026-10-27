"""Тема Fusion AMOLED: монохромный интерфейс, акцент только для фокуса и выбора."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

TOKENS = {
    "bg": "#000000",
    "surface": "#0A0A0A",
    "surface_2": "#121212",
    "surface_3": "#1C1C1C",
    "border": "#262626",
    "border_strong": "#3A3A3A",
    "text": "#F2F2F2",
    "text_muted": "#A0A0A0",
    "text_disabled": "#5A5A5A",
    "accent": "#2F7BFF",        # только фокус и выбранный элемент
    "accent_soft": "#0F2547",
    "danger": "#E5484D",
    "radius": "8px",
    "radius_lg": "12px",
    "font": "Segoe UI",
    "font_size": "10pt",
}

QSS = """
* {{ font-family: "{font}"; font-size: {font_size}; color: {text}; outline: none; }}
QMainWindow, QDialog, QWidget#Page, QStackedWidget {{ background: {bg}; }}
QToolTip {{ background: {surface_3}; color: {text}; border: 1px solid {border_strong}; padding: 4px 6px; }}
QFrame#Panel {{ background: {surface}; border: 1px solid {border}; border-radius: {radius_lg}; }}
QFrame#Banner {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {surface_2}, stop:1 #2A2A2A);
                 border: 1px solid {border}; border-radius: {radius_lg}; }}
QFrame#Separator {{ background: {border}; max-height: 1px; min-height: 1px; }}
QLabel {{ background: transparent; }}
QLabel#H1 {{ font-size: 16pt; font-weight: 600; }}
QLabel#H2 {{ font-size: 12pt; font-weight: 600; }}
QLabel#Muted {{ color: {text_muted}; }}
QLabel#Stage {{ color: {text_muted}; border: 1px dashed {border_strong}; border-radius: {radius}; padding: 2px 6px; }}
QLabel#Error {{ color: {danger}; }}

QPushButton, QToolButton {{ background: {surface_2}; border: 1px solid {border}; border-radius: {radius};
    padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: {surface_3}; border-color: {border_strong}; }}
QPushButton:pressed, QToolButton:pressed {{ background: #262626; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {accent}; }}
QPushButton:checked, QToolButton:checked {{ border: 1px solid {accent}; background: {accent_soft}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {text_disabled}; background: {surface}; border-color: {border}; }}
QPushButton#Primary {{ background: #F2F2F2; color: #000000; border: 1px solid #F2F2F2; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #FFFFFF; }}
QPushButton#Primary:focus {{ border: 2px solid {accent}; }}
QPushButton#Primary:disabled {{ background: {surface_3}; color: {text_disabled}; border-color: {border}; }}
QPushButton#Danger {{ color: {danger}; }}
QPushButton#Tile {{ border-style: dashed; border-color: {border_strong}; color: {text_muted}; }}

QToolButton#NavButton {{ background: transparent; border: 1px solid transparent; border-radius: {radius};
    padding: 6px 2px; color: {text_muted}; font-size: 8pt; }}
QToolButton#NavButton:hover {{ background: {surface_2}; color: {text}; }}
QToolButton#NavButton:checked {{ background: {surface_3}; color: {text}; border: 1px solid {accent}; }}
QToolButton#NavButton:disabled {{ color: {text_disabled}; }}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {surface_2}; border: 1px solid {border};
    border-radius: {radius}; padding: 5px 8px; selection-background-color: {accent}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {text_disabled}; }}
QComboBox QAbstractItemView {{ background: {surface_2}; border: 1px solid {border_strong};
    selection-background-color: {surface_3}; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {border_strong};
    background: {surface_2}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QCheckBox:focus, QRadioButton:focus {{ color: #FFFFFF; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {text_disabled}; }}

QListWidget, QTreeWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border-radius: {radius}; padding: 4px; }}
QListWidget::item:hover {{ background: {surface_2}; }}
QListWidget::item:selected {{ background: {surface_3}; border: 1px solid {accent}; color: {text}; }}
QListWidget#Cards::item {{ background: {surface}; border: 1px solid {border}; margin: 4px; }}
QListWidget#Cards::item:hover {{ border-color: {border_strong}; }}
QListWidget#Cards::item:selected {{ border: 1px solid {accent}; background: {surface_2}; }}

QMenuBar {{ background: {bg}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {surface_3}; border-radius: 6px; }}
QMenu {{ background: {surface_2}; border: 1px solid {border_strong}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {surface_3}; }}
QMenu::item:disabled {{ color: {text_disabled}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}
QStatusBar {{ background: {bg}; border-top: 1px solid {border}; color: {text_muted}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle {{ background: {border_strong}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QProgressBar {{ background: {surface_3}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: #D0D0D0; border-radius: 3px; }}
QScrollArea {{ background: transparent; border: none; }}
QMessageBox {{ background: {surface}; }}
QDockWidget {{ color: {text_muted}; titlebar-close-icon: none; }}
QDockWidget::title {{ background: {surface}; padding: 6px 10px; border-bottom: 1px solid {border}; }}
QDockWidget > QWidget {{ background: {surface}; }}
QMainWindow::separator {{ background: {border}; width: 1px; height: 1px; }}
QTreeWidget {{ color: {text}; }}
QDoubleSpinBox {{ background: {surface_2}; border: 1px solid {border}; border-radius: {radius}; padding: 4px 6px; }}
QDoubleSpinBox:focus {{ border: 1px solid {accent}; }}
QFontComboBox {{ min-width: 120px; }}
"""


def stylesheet() -> str:
    return QSS.format(**TOKENS)


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    t = TOKENS
    pal = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, t["bg"]), (QPalette.ColorRole.WindowText, t["text"]),
        (QPalette.ColorRole.Base, t["surface_2"]), (QPalette.ColorRole.AlternateBase, t["surface"]),
        (QPalette.ColorRole.Text, t["text"]), (QPalette.ColorRole.Button, t["surface_2"]),
        (QPalette.ColorRole.ButtonText, t["text"]), (QPalette.ColorRole.Highlight, t["accent"]),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"), (QPalette.ColorRole.ToolTipBase, t["surface_3"]),
        (QPalette.ColorRole.ToolTipText, t["text"]), (QPalette.ColorRole.PlaceholderText, t["text_disabled"]),
        (QPalette.ColorRole.Link, t["text"]),
    ]:
        pal.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["text_disabled"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())
