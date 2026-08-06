"""Qt printing for completed 4R sheet images."""

from __future__ import annotations

from enum import Enum, auto

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import QDialog, QWidget

from core.layout import LayoutResult


class PrintOutcome(Enum):
    PRINTED = auto()
    CANCELLED = auto()
    NO_PRINTER = auto()


def print_sheet(
    sheet_image: Image.Image,
    layout: LayoutResult,
    parent: QWidget | None = None,
) -> PrintOutcome:
    """Open the system print dialog and print one full-page 4R sheet."""
    if not QPrinterInfo.availablePrinters():
        return PrintOutcome.NO_PRINTER

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(
        QPageSize(
            QSizeF(102, 152),
            QPageSize.Unit.Millimeter,
            "4R",
        )
    )
    orientation = (
        QPageLayout.Orientation.Landscape
        if layout.paper_width_mm > layout.paper_height_mm
        else QPageLayout.Orientation.Portrait
    )
    printer.setPageOrientation(orientation)
    printer.setFullPage(True)
    printer.setPageMargins(
        QMarginsF(0, 0, 0, 0),
        QPageLayout.Unit.Millimeter,
    )

    dialog = QPrintDialog(printer, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return PrintOutcome.CANCELLED

    qimage = ImageQt(sheet_image.convert("RGBA")).copy()
    target = printer.pageLayout().fullRectPixels(printer.resolution())
    painter = QPainter(printer)
    try:
        painter.drawImage(target, qimage)
    finally:
        painter.end()
    return PrintOutcome.PRINTED
