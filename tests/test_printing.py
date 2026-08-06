import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtGui import QColorSpace, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog
from PySide6.QtWidgets import QApplication, QDialog

from core.layout import solve_layout
from ui import printing as printing_module
from ui.printing import PrintOutcome, print_sheet


class PrintingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_reports_no_printer_without_opening_a_dialog(self) -> None:
        sheet = Image.new("RGB", (1205, 1795), "white")
        layout = solve_layout(25, 35)

        with (
            patch("ui.printing.QPrinterInfo.availablePrinters", return_value=[]),
            patch.object(QPrintDialog, "exec") as dialog_exec,
        ):
            outcome = print_sheet(sheet, layout)

        self.assertIs(outcome, PrintOutcome.NO_PRINTER)
        dialog_exec.assert_not_called()

    def test_prepared_print_image_is_opaque_srgb_300dpi_and_preserves_blue(
        self,
    ) -> None:
        prepare_print_image = getattr(
            printing_module,
            "_prepare_print_image",
            None,
        )
        self.assertIsNotNone(prepare_print_image)
        if prepare_print_image is None:
            return
        source = Image.new("RGBA", (24, 36), (67, 142, 219, 128))

        qimage = prepare_print_image(source)

        expected_srgb = QColorSpace(QColorSpace.NamedColorSpace.SRgb)
        self.assertFalse(qimage.hasAlphaChannel())
        self.assertTrue(qimage.colorSpace().isValid())
        self.assertEqual(qimage.colorSpace(), expected_srgb)
        self.assertEqual(qimage.dotsPerMeterX(), 11811)
        self.assertEqual(qimage.dotsPerMeterY(), 11811)
        self.assertEqual(qimage.pixelColor(0, 0).getRgb()[:3], (67, 142, 219))

    def test_cancelled_dialog_does_not_draw(self) -> None:
        sheet = Image.new("RGB", (1205, 1795), "white")
        layout = solve_layout(25, 35)

        with (
            patch(
                "ui.printing.QPrinterInfo.availablePrinters",
                return_value=[object()],
            ),
            patch.object(
                QPrintDialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ),
            patch("ui.printing.QPainter") as painter_class,
        ):
            outcome = print_sheet(sheet, layout)

        self.assertIs(outcome, PrintOutcome.CANCELLED)
        painter_class.assert_not_called()

    def test_enables_full_page_before_requesting_zero_margins(self) -> None:
        sheet = Image.new("RGB", (1205, 1795), "white")
        layout = solve_layout(25, 35)

        with (
            patch(
                "ui.printing.QPrinterInfo.availablePrinters",
                return_value=[object()],
            ),
            patch("ui.printing.QPrinter") as printer_class,
            patch("ui.printing.QPrintDialog") as dialog_class,
        ):
            dialog_class.return_value.exec.return_value = QDialog.DialogCode.Rejected
            outcome = print_sheet(sheet, layout)

        self.assertIs(outcome, PrintOutcome.CANCELLED)
        method_names = [call[0] for call in printer_class.return_value.method_calls]
        self.assertLess(
            method_names.index("setFullPage"),
            method_names.index("setPageMargins"),
        )

    def test_prints_full_page_in_the_layout_orientation(self) -> None:
        cases = (
            (solve_layout(25, 35), QPageLayout.Orientation.Portrait),
            (solve_layout(55, 84), QPageLayout.Orientation.Landscape),
        )

        for layout, expected_orientation in cases:
            with self.subTest(orientation=expected_orientation):
                sheet = Image.new(
                    "RGB",
                    (
                        1795 if layout.paper_width_mm > layout.paper_height_mm else 1205,
                        1205 if layout.paper_width_mm > layout.paper_height_mm else 1795,
                    ),
                    "white",
                )
                with (
                    patch(
                        "ui.printing.QPrinterInfo.availablePrinters",
                        return_value=[object()],
                    ),
                    patch.object(
                        QPrintDialog,
                        "exec",
                        return_value=QDialog.DialogCode.Accepted,
                    ),
                    patch("ui.printing.QPainter") as painter_class,
                ):
                    painter_class.RenderHint = QPainter.RenderHint
                    outcome = print_sheet(sheet, layout)

                self.assertIs(outcome, PrintOutcome.PRINTED)
                printer = painter_class.call_args.args[0]
                page_layout = printer.pageLayout()
                self.assertTrue(printer.fullPage())
                self.assertIs(page_layout.orientation(), expected_orientation)

                page_size = page_layout.pageSize().size(QPageSize.Unit.Millimeter)
                self.assertAlmostEqual(page_size.width(), 102.0, delta=0.01)
                self.assertAlmostEqual(page_size.height(), 152.0, delta=0.01)

                margins = page_layout.margins(QPageLayout.Unit.Millimeter)
                self.assertEqual(
                    (margins.left(), margins.top(), margins.right(), margins.bottom()),
                    (0.0, 0.0, 0.0, 0.0),
                )

                painter = painter_class.return_value
                painter.setRenderHint.assert_called_once_with(
                    QPainter.RenderHint.SmoothPixmapTransform,
                    True,
                )
                painter.drawImage.assert_called_once()
                target, qimage, source = painter.drawImage.call_args.args
                self.assertEqual(
                    target,
                    page_layout.fullRectPixels(printer.resolution()),
                )
                self.assertEqual((qimage.width(), qimage.height()), sheet.size)
                self.assertEqual(source, qimage.rect())


if __name__ == "__main__":
    unittest.main()
