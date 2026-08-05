import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from core.crop import CropBox
from ui.crop_view import CropView


class CropViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.image = Image.new("RGB", (1000, 1200), (80, 100, 120))
        self.auto_box = CropBox(200, 200, 600, 760)
        self.view = CropView()
        self.view.resize(500, 600)
        self.view.show()
        self.view.set_content(self.image, self.auto_box, 5 / 7)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def image_point(self, x: float, y: float):
        return self.view._image_to_widget(QPointF(x, y)).toPoint()

    def drag(self, start, end) -> None:
        QTest.mousePress(
            self.view,
            Qt.MouseButton.LeftButton,
            pos=start,
        )
        QTest.mouseMove(self.view, end)
        QTest.mouseRelease(
            self.view,
            Qt.MouseButton.LeftButton,
            pos=end,
        )
        self.app.processEvents()

    def test_whole_box_drag_emits_live_and_finished_updates(self) -> None:
        changed = QSignalSpy(self.view.cropBoxChanged)
        finished = QSignalSpy(self.view.interactionFinished)

        self.drag(
            self.image_point(400, 480),
            self.image_point(500, 580),
        )

        self.assertEqual(self.view.crop_box, CropBox(300, 300, 700, 860))
        self.assertGreaterEqual(changed.count(), 1)
        self.assertEqual(finished.count(), 1)

    def test_whole_box_drag_is_clamped_to_image_boundary(self) -> None:
        self.drag(
            self.image_point(400, 480),
            self.image_point(1400, 1480),
        )

        box = self.view.crop_box
        self.assertEqual(box.right, self.image.width)
        self.assertEqual(box.bottom, self.image.height)
        self.assertEqual(box.width / box.height, 5 / 7)

    def test_each_corner_resizes_with_locked_ratio_and_fixed_opposite_corner(self) -> None:
        cases = {
            "top_left": ((200, 200), (240, 256), (600, 760)),
            "top_right": ((600, 200), (560, 256), (200, 760)),
            "bottom_right": ((600, 760), (560, 704), (200, 200)),
            "bottom_left": ((200, 760), (240, 704), (600, 200)),
        }
        for name, (start, end, fixed_corner) in cases.items():
            with self.subTest(corner=name):
                self.view.set_content(self.image, self.auto_box, 5 / 7)
                self.drag(self.image_point(*start), self.image_point(*end))

                box = self.view.crop_box
                self.assertAlmostEqual(box.width / box.height, 5 / 7)
                self.assertGreaterEqual(box.left, 0)
                self.assertGreaterEqual(box.top, 0)
                self.assertLessEqual(box.right, self.image.width)
                self.assertLessEqual(box.bottom, self.image.height)
                corners = {
                    "top_left": (box.right, box.bottom),
                    "top_right": (box.left, box.bottom),
                    "bottom_right": (box.left, box.top),
                    "bottom_left": (box.right, box.top),
                }
                actual_fixed = corners[name]
                self.assertAlmostEqual(actual_fixed[0], fixed_corner[0])
                self.assertAlmostEqual(actual_fixed[1], fixed_corner[1])

    def test_corner_resize_cannot_cross_image_boundary(self) -> None:
        self.drag(
            self.image_point(600, 760),
            self.image_point(1400, 1600),
        )

        box = self.view.crop_box
        self.assertAlmostEqual(box.width / box.height, 5 / 7)
        self.assertLessEqual(box.right, self.image.width)
        self.assertEqual(box.bottom, self.image.height)

    def test_reset_restores_automatic_box_and_emits_finish(self) -> None:
        self.drag(
            self.image_point(400, 480),
            self.image_point(500, 580),
        )
        finished = QSignalSpy(self.view.interactionFinished)

        self.view.reset_to_auto()

        self.assertEqual(self.view.crop_box, self.auto_box)
        self.assertEqual(finished.count(), 1)

    def test_new_content_replaces_ratio_and_automatic_box(self) -> None:
        new_box = CropBox(100, 100, 500, 700)

        self.view.set_content(self.image, new_box, 2 / 3)

        self.assertEqual(self.view.crop_box, new_box)
        self.assertAlmostEqual(
            self.view.crop_box.width / self.view.crop_box.height,
            2 / 3,
        )
        self.assertFalse(self.view.pixmap().isNull())

    def test_crop_overlay_uses_dark_mask_and_white_corner_marks(self) -> None:
        rendered = self.view.grab().toImage()
        outside = rendered.pixelColor(self.image_point(100, 100))
        inside = rendered.pixelColor(self.image_point(400, 480))
        corner = self.image_point(200, 200)
        corner_mark = rendered.pixelColor(corner)
        diagonal_inside = rendered.pixelColor(corner + QPoint(3, 3))

        self.assertAlmostEqual(CropView.MASK_OPACITY, 0.55)
        self.assertAlmostEqual(CropView.FRAME_OPACITY, 0.70)
        self.assertEqual(CropView.CORNER_MARK_LENGTH, 18.0)
        self.assertEqual(CropView.CORNER_MARK_WIDTH, 2.5)
        for actual, expected in zip(outside.getRgb()[:3], (36, 45, 54)):
            self.assertAlmostEqual(actual, expected, delta=2)
        self.assertEqual(inside.getRgb()[:3], (80, 100, 120))
        self.assertGreater(min(corner_mark.getRgb()[:3]), 230)
        self.assertEqual(diagonal_inside.getRgb()[:3], (80, 100, 120))

    def test_empty_state_uses_short_darkroom_instruction(self) -> None:
        self.assertEqual(
            CropView.EMPTY_TEXT,
            "拖入照片，或点击右上导入",
        )


if __name__ == "__main__":
    unittest.main()
