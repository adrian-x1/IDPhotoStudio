"""Darkroom visual theme for the desktop interface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


COLORS = {
    "background": "#17181A",
    "surface": "#1F2124",
    "surface_muted": "#282B2F",
    "control": "#282B2F",
    "control_hover": "#31353A",
    "preview_background": "#1F2124",
    "text": "#E8E6E3",
    "muted_text": "#9A9A96",
    "border": "#34383D",
    "border_strong": "#34383D",
    "primary": "#E8B04B",
    "primary_hover": "#F0C674",
    "primary_pressed": "#CF9530",
    "focus": "#E8B04B",
    "on_primary": "#17181A",
    "warning_background": "rgba(232, 176, 75, 20)",
    "warning_border": "rgba(232, 176, 75, 72)",
    "warning_text": "#F0C674",
}

_ICON_DIR = Path(__file__).resolve().parent / "icons"
CONTROL_ICON_PATHS = {
    "chevron_down": _ICON_DIR / "chevron-down.svg",
    "spin_up": _ICON_DIR / "spin-up.svg",
    "spin_down": _ICON_DIR / "spin-down.svg",
    "checkmark": _ICON_DIR / "checkmark.svg",
}


def _icon_url(name: str) -> str:
    return CONTROL_ICON_PATHS[name].as_posix()


APP_STYLESHEET = f"""
QWidget {{
    color: {COLORS["text"]};
    font-size: 13px;
    selection-color: {COLORS["on_primary"]};
    selection-background-color: {COLORS["primary"]};
}}

QMainWindow,
QWidget#appShell {{
    background: {COLORS["background"]};
}}

QWidget#appShell {{
    border: 1px solid transparent;
}}

QWidget#appShell[dragActive="true"] {{
    border: 1px dashed {COLORS["focus"]};
}}

QWidget#headerPanel {{
    background: transparent;
}}

QFrame[card="true"] {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
}}

QFrame#outputSeparator {{
    color: {COLORS["border"]};
}}

QLabel#appTitle {{
    color: {COLORS["text"]};
    font-size: 21px;
    font-weight: 700;
}}

QLabel#appSubtitle,
QLabel#cardSubtitle,
QLabel#statusLabel {{
    color: {COLORS["muted_text"]};
}}

QLabel#appSubtitle {{
    font-size: 12px;
}}

QLabel#cardTitle,
QLabel#sectionTitle {{
    color: {COLORS["text"]};
    font-size: 14px;
    font-weight: 600;
}}

QLabel#cardSubtitle,
QLabel#fieldLabel,
QLabel#statusLabel {{
    font-size: 12px;
}}

QLabel#fieldLabel {{
    color: {COLORS["muted_text"]};
    font-weight: 500;
}}

QLabel#countBadge {{
    color: {COLORS["primary"]};
    background: transparent;
    border: 0;
    font-weight: 600;
}}

QLabel#countNumber {{
    color: {COLORS["primary"]};
    font-size: 64px;
    font-weight: 700;
}}

QLabel#countUnit {{
    color: {COLORS["muted_text"]};
    font-size: 12px;
}}

QLabel#paperPreview {{
    color: {COLORS["muted_text"]};
    background: transparent;
    border: 0;
}}

QFrame#statusBar {{
    background: transparent;
    border-top: 1px solid {COLORS["border"]};
}}

QLabel#warningLabel {{
    color: {COLORS["warning_text"]};
    background: {COLORS["warning_background"]};
    border: 1px solid {COLORS["warning_border"]};
    border-radius: 8px;
    padding: 7px 10px;
}}

QWidget#previewCanvas {{
    color: {COLORS["muted_text"]};
    background: {COLORS["preview_background"]};
    border: 0;
}}

QPushButton {{
    min-height: 34px;
    padding: 0 14px;
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    font-weight: 500;
}}

QPushButton:hover {{
    background: {COLORS["control_hover"]};
}}

QPushButton:pressed {{
    background: {COLORS["border"]};
}}

QPushButton[variant="primary"] {{
    color: {COLORS["on_primary"]};
    background: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
    font-weight: 600;
}}

QPushButton[variant="primary"]:hover {{
    background: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}

QPushButton[variant="primary"]:pressed {{
    background: {COLORS["primary_pressed"]};
    border-color: {COLORS["primary_pressed"]};
}}

QPushButton[variant="quiet"] {{
    min-height: 30px;
    padding: 0 8px;
    color: {COLORS["muted_text"]};
    background: transparent;
    border-color: transparent;
}}

QPushButton[variant="quiet"]:hover {{
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border-color: {COLORS["border"]};
}}

QPushButton:disabled {{
    color: #666865;
    background: {COLORS["control"]};
    border-color: {COLORS["border"]};
}}

QPushButton:focus,
QComboBox:focus,
QDoubleSpinBox:focus,
QRadioButton:focus,
QCheckBox:focus {{
    border: 1px solid {COLORS["focus"]};
}}

QComboBox {{
    min-height: 34px;
    padding: 0 32px 0 10px;
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}

QComboBox:hover {{
    background: {COLORS["control_hover"]};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    background: transparent;
    border: 0;
}}

QComboBox::down-arrow {{
    image: url({_icon_url("chevron_down")});
    width: 10px;
    height: 6px;
}}

QComboBox QAbstractItemView {{
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    selection-color: {COLORS["on_primary"]};
    selection-background-color: {COLORS["primary"]};
}}

QDoubleSpinBox {{
    min-height: 34px;
    padding: 0 28px 0 10px;
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}

QDoubleSpinBox:hover {{
    background: {COLORS["control_hover"]};
}}

QDoubleSpinBox::up-button,
QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 22px;
    background: transparent;
    border: 0;
}}

QDoubleSpinBox::up-button {{
    subcontrol-position: top right;
}}

QDoubleSpinBox::down-button {{
    subcontrol-position: bottom right;
}}

QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {{
    background: {COLORS["control_hover"]};
}}

QDoubleSpinBox::up-arrow {{
    image: url({_icon_url("spin_up")});
    width: 7px;
    height: 5px;
}}

QDoubleSpinBox::down-arrow {{
    image: url({_icon_url("spin_down")});
    width: 7px;
    height: 5px;
}}

QRadioButton[segment="true"] {{
    min-height: 34px;
    padding: 0 9px;
    spacing: 6px;
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 0;
    font-size: 11px;
}}

QRadioButton[segment="true"]:hover {{
    background: {COLORS["control_hover"]};
}}

QRadioButton[segment="true"]:checked {{
    color: {COLORS["text"]};
    background: rgba(232, 176, 75, 31);
    border: 1px solid {COLORS["primary"]};
}}

QRadioButton#backgroundOriginal {{
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}}

QRadioButton#backgroundRed {{
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}}

QRadioButton#backgroundOriginal::indicator {{
    width: 0;
    height: 0;
}}

QRadioButton#backgroundWhite::indicator,
QRadioButton#backgroundBlue::indicator,
QRadioButton#backgroundRed::indicator {{
    subcontrol-origin: content;
    subcontrol-position: center;
    width: 12px;
    height: 12px;
    margin: 0;
    border-radius: 6px;
    border: 1px solid rgba(232, 230, 227, 90);
}}

QRadioButton#backgroundWhite::indicator {{
    background: #FFFFFF;
}}

QRadioButton#backgroundBlue::indicator {{
    background: #438EDB;
}}

QRadioButton#backgroundRed::indicator {{
    background: #FF0000;
}}

QCheckBox {{
    min-height: 30px;
    padding: 1px 4px;
    spacing: 7px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}

QCheckBox:hover {{
    background: {COLORS["control_hover"]};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
}}

QCheckBox::indicator:checked {{
    image: url({_icon_url("checkmark")});
    background: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
}}

QProgressBar {{
    min-height: 2px;
    max-height: 2px;
    background: {COLORS["border"]};
    border: 0;
}}

QProgressBar::chunk {{
    background: {COLORS["primary"]};
}}

QSplitter::handle {{
    background: transparent;
}}

QSplitter::handle:hover {{
    background: {COLORS["border"]};
}}

QToolTip {{
    color: {COLORS["text"]};
    background: {COLORS["control"]};
    border: 1px solid {COLORS["border"]};
    padding: 5px 8px;
}}
"""


def apply_theme(application: QApplication) -> None:
    """Apply the shared darkroom theme to the current Qt application."""
    palette = application.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["background"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["control"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["control"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["on_primary"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLORS["control"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["text"]))
    if hasattr(QPalette.ColorRole, "Accent"):
        palette.setColor(QPalette.ColorRole.Accent, QColor(COLORS["primary"]))
    application.setPalette(palette)
    application.setStyleSheet(APP_STYLESHEET)
