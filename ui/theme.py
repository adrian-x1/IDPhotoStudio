"""Warm neutral visual theme for the desktop interface."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


COLORS = {
    "background": "#F7F4ED",
    "surface": "#FFFFFF",
    "surface_muted": "#F0ECE4",
    "preview_background": "#EAE5DB",
    "text": "#2D2A26",
    "muted_text": "#6F6A61",
    "border": "#DED8CD",
    "border_strong": "#C9C1B4",
    "primary": "#B85C3B",
    "primary_hover": "#A84F32",
    "primary_pressed": "#9A452C",
    "focus": "#B85C3B",
    "warning_background": "#FFF3DF",
    "warning_border": "#E3B876",
    "warning_text": "#70451F",
}


APP_STYLESHEET = f"""
QWidget {{
    color: {COLORS["text"]};
    font-size: 13px;
}}

QMainWindow,
QWidget#appShell {{
    background: {COLORS["background"]};
}}

QWidget#appShell {{
    border: 2px solid transparent;
}}

QWidget#appShell[dragActive="true"] {{
    border: 2px dashed {COLORS["focus"]};
}}

QWidget#headerPanel {{
    background: transparent;
}}

QFrame[card="true"] {{
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 14px;
}}

QFrame#outputSeparator {{
    color: {COLORS["border"]};
}}

QLabel#appTitle {{
    color: {COLORS["text"]};
    font-size: 23px;
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
    color: {COLORS["text"]};
    background: {COLORS["surface_muted"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 11px;
    padding: 3px 10px;
    font-weight: 600;
}}

QLabel#warningLabel {{
    color: {COLORS["warning_text"]};
    background: {COLORS["warning_background"]};
    border: 1px solid {COLORS["warning_border"]};
    border-radius: 10px;
    padding: 8px 12px;
}}

QWidget#previewCanvas {{
    background: {COLORS["preview_background"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
}}

QPushButton {{
    min-height: 36px;
    padding: 0 14px;
    color: {COLORS["text"]};
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 10px;
    font-weight: 500;
}}

QPushButton:hover {{
    background: {COLORS["surface_muted"]};
    border-color: {COLORS["muted_text"]};
}}

QPushButton:pressed {{
    background: {COLORS["border"]};
}}

QPushButton[variant="primary"] {{
    color: #FFFFFF;
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
    padding: 0 10px;
    color: {COLORS["muted_text"]};
    background: transparent;
    border-color: transparent;
}}

QPushButton[variant="quiet"]:hover {{
    color: {COLORS["text"]};
    background: {COLORS["surface_muted"]};
    border-color: {COLORS["border"]};
}}

QPushButton:disabled {{
    color: {COLORS["muted_text"]};
    background: {COLORS["surface_muted"]};
    border-color: {COLORS["border"]};
}}

QComboBox,
QDoubleSpinBox {{
    min-height: 34px;
    padding: 0 10px;
    color: {COLORS["text"]};
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    border-radius: 8px;
    selection-background-color: {COLORS["primary"]};
}}

QComboBox:hover,
QDoubleSpinBox:hover {{
    border-color: {COLORS["muted_text"]};
}}

QPushButton:focus,
QComboBox:focus,
QDoubleSpinBox:focus,
QRadioButton:focus,
QCheckBox:focus {{
    border: 2px solid {COLORS["focus"]};
}}

QRadioButton,
QCheckBox {{
    min-height: 30px;
    padding: 1px 6px;
    border: 2px solid transparent;
    border-radius: 8px;
    spacing: 6px;
}}

QRadioButton:hover,
QCheckBox:hover {{
    background: {COLORS["surface_muted"]};
}}

QProgressBar {{
    min-height: 4px;
    max-height: 4px;
    background: {COLORS["border"]};
    border: 0;
    border-radius: 2px;
}}

QProgressBar::chunk {{
    background: {COLORS["primary"]};
    border-radius: 2px;
}}

QSplitter::handle {{
    background: transparent;
}}

QSplitter::handle:hover {{
    background: {COLORS["border"]};
}}

QToolTip {{
    color: {COLORS["text"]};
    background: {COLORS["surface"]};
    border: 1px solid {COLORS["border_strong"]};
    padding: 5px 8px;
}}
"""


def apply_theme(application: QApplication) -> None:
    """Apply the shared light theme to the current Qt application."""
    palette = application.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    if hasattr(QPalette.ColorRole, "Accent"):
        palette.setColor(QPalette.ColorRole.Accent, QColor(COLORS["primary"]))
    application.setPalette(palette)
    application.setStyleSheet(APP_STYLESHEET)
