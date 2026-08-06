import os
import random
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from core.crop import CropBox, TargetSize, integer_crop_bounds
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
        self.target = TargetSize(25, 35)
        self.view.set_content(
            self.image,
            self.auto_box,
            5 / 7,
            target_size=self.target,
        )
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

    def wheel(
        self,
        steps: int,
        modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    ) -> None:
        position = QPointF(self.view.rect().center())
        event = QWheelEvent(
            position,
            self.view.mapToGlobal(position.toPoint()),
            QPoint(),
            QPoint(0, 120 * steps),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        self.app.sendEvent(self.view, event)
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
                self.view.set_content(
                    self.image,
                    self.auto_box,
                    5 / 7,
                    target_size=self.target,
                )
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

        self.view.set_content(
            self.image,
            new_box,
            2 / 3,
            target_size=TargetSize(2, 3),
        )

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

    def test_wheel_scales_from_center_and_emits_both_discrete_signals(self) -> None:
        changed = QSignalSpy(self.view.cropBoxChanged)
        finished = QSignalSpy(self.view.interactionFinished)
        center_before = (
            (self.auto_box.left + self.auto_box.right) / 2,
            (self.auto_box.top + self.auto_box.bottom) / 2,
        )

        self.wheel(1)

        box = self.view.crop_box
        self.assertAlmostEqual(box.width, self.auto_box.width * 1.02)
        self.assertAlmostEqual(box.height, box.width / (5 / 7))
        self.assertAlmostEqual((box.left + box.right) / 2, center_before[0])
        self.assertAlmostEqual((box.top + box.bottom) / 2, center_before[1])
        self.assertEqual(changed.count(), 1)
        self.assertEqual(finished.count(), 1)

        self.view.set_content(
            self.image,
            self.auto_box,
            5 / 7,
            target_size=self.target,
        )
        self.wheel(1, Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(self.view.crop_box.width, self.auto_box.width * 1.005)

    def test_arrow_keys_move_in_image_pixels_and_emit_both_signals(self) -> None:
        changed = QSignalSpy(self.view.cropBoxChanged)
        finished = QSignalSpy(self.view.interactionFinished)

        QTest.keyClick(self.view, Qt.Key.Key_Left)
        QTest.keyClick(
            self.view,
            Qt.Key.Key_Down,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.app.processEvents()

        self.assertEqual(self.view.crop_box, CropBox(199, 210, 599, 770))
        self.assertEqual(changed.count(), 2)
        self.assertEqual(finished.count(), 2)

    def test_crop_size_text_matches_shared_integer_bounds_and_warns_below_300dpi(self) -> None:
        bounds = integer_crop_bounds(
            self.auto_box,
            self.image.width,
            self.image.height,
            5 / 7,
        )

        self.assertEqual(
            self.view.crop_pixel_size,
            (bounds[2] - bounds[0], bounds[3] - bounds[1]),
        )
        self.assertEqual(self.view.crop_size_text, "400 × 560")
        self.assertFalse(self.view.crop_size_is_insufficient)

        small_box = CropBox(200, 200, 400, 480)
        self.view.set_content(
            self.image,
            small_box,
            5 / 7,
            target_size=self.target,
        )
        self.assertEqual(self.view.crop_size_text, "200 × 280")
        self.assertTrue(self.view.crop_size_is_insufficient)

    def test_seeded_mixed_interactions_preserve_ratio_for_every_emitted_box(self) -> None:
        generator = random.Random(20260806)
        emitted: list[CropBox] = []
        self.view.cropBoxChanged.connect(emitted.append)
        self.view.interactionFinished.connect(emitted.append)
        corners = ("top_left", "top_right", "bottom_right", "bottom_left")
        keys = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)

        for _ in range(50):
            self.view.set_content(
                self.image,
                self.auto_box,
                5 / 7,
                target_size=self.target,
            )
            emitted.clear()
            for corner in corners:
                start = self.view._handle_points()[corner].toPoint()
                end = start + QPoint(
                    generator.randint(-12, 12),
                    generator.randint(-12, 12),
                )
                self.drag(start, end)
            crop_rect = self.view._crop_rect_widget()
            offset = QPoint(generator.randint(-8, 8), generator.randint(-8, 8))
            self.drag(crop_rect.center().toPoint(), crop_rect.center().toPoint() + offset)
            self.wheel(generator.choice((-1, 1)))
            self.wheel(
                generator.choice((-1, 1)),
                Qt.KeyboardModifier.ShiftModifier,
            )
            QTest.keyClick(self.view, generator.choice(keys))
            QTest.keyClick(
                self.view,
                generator.choice(keys),
                Qt.KeyboardModifier.ShiftModifier,
            )
            self.app.processEvents()

            self.assertGreater(len(emitted), 0)
            for box in emitted:
                self.assertLess(abs(box.width / box.height - 5 / 7), 1e-6)
                self.assertGreaterEqual(box.left, 0.0)
                self.assertGreaterEqual(box.top, 0.0)
                self.assertLessEqual(box.right, self.image.width)
                self.assertLessEqual(box.bottom, self.image.height)


if __name__ == "__main__":
    unittest.main()
