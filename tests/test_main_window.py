import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGraphicsDropShadowEffect,
    QRadioButton,
)

from core.crop import (
    CropBox,
    FaceGeometry,
    Point,
    TargetSize,
    calculate_crop_box,
)
from core.layout import compose_sheet
from ui.main_window import IMAGE_FILE_FILTER, SUPPORTED_IMAGE_SUFFIXES, MainWindow


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.image_path = Path(self.temp_dir.name) / "portrait.jpg"
        Image.new("RGB", (1000, 1200), (80, 100, 120)).save(self.image_path)
        self.face = FaceGeometry(
            bbox_width=400.0,
            eyes_center=Point(500.0, 500.0),
        )
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def load_portrait(self) -> bool:
        with patch("ui.main_window.detect_face", return_value=self.face):
            return self.window.load_image(self.image_path)

    def wait_until(self, condition, timeout_ms: int = 3000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not condition():
            if time.monotonic() >= deadline:
                self.fail("timed out waiting for UI condition")
            self.app.processEvents()
            QTest.qWait(10)

    @staticmethod
    def mime_with_urls(*urls: QUrl) -> QMimeData:
        mime = QMimeData()
        mime.setUrls(list(urls))
        return mime

    @classmethod
    def drag_enter_event(cls, *urls: QUrl) -> QDragEnterEvent:
        mime = cls.mime_with_urls(*urls)
        event = QDragEnterEvent(
            QPoint(12, 12),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        event._test_mime_data = mime
        return event

    @classmethod
    def drop_event(cls, *urls: QUrl) -> QDropEvent:
        mime = cls.mime_with_urls(*urls)
        event = QDropEvent(
            QPointF(12, 12),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        event._test_mime_data = mime
        return event

    def test_default_original_background_loads_all_three_previews(self) -> None:
        self.assertEqual(self.window.spec_combo.currentText(), "一寸")
        self.assertTrue(self.window.original_background_radio.isChecked())
        self.assertEqual(self.window.gap_spin.value(), 1.0)
        self.assertEqual(self.window.margin_spin.value(), 1.0)
        self.assertTrue(self.window.cut_lines_check.isChecked())

        with patch("ui.matting_worker.extract_foreground") as extract_foreground:
            self.assertTrue(self.load_portrait())

        self.assertFalse(self.window.original_preview.pixmap().isNull())
        self.assertFalse(self.window.crop_preview.pixmap().isNull())
        self.assertFalse(self.window.sheet_preview.pixmap().isNull())
        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertEqual(self.window.status_label.text(), "保持原底，未执行抠图")
        extract_foreground.assert_not_called()

    def test_image_suffixes_are_shared_with_the_file_dialog_filter(self) -> None:
        expected = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
        )

        self.assertEqual(SUPPORTED_IMAGE_SUFFIXES, expected)
        self.assertEqual(
            IMAGE_FILE_FILTER,
            "照片 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)",
        )

    def test_background_choices_remain_radio_buttons_with_segment_styles(self) -> None:
        self.assertIsInstance(self.window.background_group, QButtonGroup)
        self.assertTrue(self.window.background_group.exclusive())
        radios = (
            self.window.original_background_radio,
            self.window.white_background_radio,
            self.window.blue_background_radio,
            self.window.red_background_radio,
        )
        self.assertEqual(
            [radio.objectName() for radio in radios],
            ["backgroundOriginal", "backgroundWhite", "backgroundBlue", "backgroundRed"],
        )
        self.assertEqual(self.window.original_background_radio.text(), "原底")
        self.assertEqual(
            self.window.original_background_radio.accessibleName(),
            "保持原底",
        )
        for radio in radios:
            with self.subTest(radio=radio.objectName()):
                self.assertIsInstance(radio, QRadioButton)
                self.assertTrue(radio.property("segment"))

    def test_drag_enter_only_accepts_supported_local_files(self) -> None:
        valid = self.drag_enter_event(QUrl.fromLocalFile(str(self.image_path)))
        self.window.dragEnterEvent(valid)
        self.assertTrue(valid.isAccepted())

        invalid_urls = (
            QUrl.fromLocalFile(str(Path(self.temp_dir.name))),
            QUrl.fromLocalFile(str(Path(self.temp_dir.name) / "notes.txt")),
            QUrl("https://example.com/portrait.jpg"),
        )
        for url in invalid_urls:
            with self.subTest(url=url.toString()):
                event = self.drag_enter_event(url)
                self.window.dragEnterEvent(event)
                self.assertFalse(event.isAccepted())

    def test_valid_drag_highlight_clears_on_leave(self) -> None:
        shell = getattr(self.window, "app_shell", None)
        self.assertIsNotNone(shell)
        event = self.drag_enter_event(QUrl.fromLocalFile(str(self.image_path)))

        self.window.dragEnterEvent(event)
        self.assertTrue(shell.property("dragActive"))

        self.window.dragLeaveEvent(QDragLeaveEvent())
        self.assertFalse(shell.property("dragActive"))

    def test_drop_loads_only_the_first_local_image(self) -> None:
        second_path = Path(self.temp_dir.name) / "second.png"
        Image.new("RGB", (500, 700), (200, 30, 40)).save(second_path)
        event = self.drop_event(
            QUrl.fromLocalFile(str(self.image_path)),
            QUrl.fromLocalFile(str(second_path)),
        )

        with (
            patch("ui.main_window.detect_face", return_value=self.face),
            patch.object(
                self.window,
                "load_image",
                wraps=self.window.load_image,
            ) as load_image,
        ):
            self.window.dropEvent(event)

        self.assertTrue(event.isAccepted())
        load_image.assert_called_once_with(self.image_path)
        self.assertEqual(self.window.source_image.size, (1000, 1200))

    def test_drop_ignores_invalid_first_item_and_accepts_uppercase_suffix(self) -> None:
        text_path = Path(self.temp_dir.name) / "notes.txt"
        text_path.write_text("not a photo", encoding="utf-8")
        invalid = self.drop_event(
            QUrl.fromLocalFile(str(text_path)),
            QUrl.fromLocalFile(str(self.image_path)),
        )

        with patch.object(self.window, "load_image") as load_image:
            self.window.dropEvent(invalid)

        self.assertFalse(invalid.isAccepted())
        load_image.assert_not_called()

        uppercase_path = Path(self.temp_dir.name) / "PORTRAIT.JPG"
        Image.new("RGB", (640, 800), (20, 100, 160)).save(uppercase_path)
        valid = self.drop_event(QUrl.fromLocalFile(str(uppercase_path)))
        with patch("ui.main_window.detect_face", return_value=self.face):
            self.window.dropEvent(valid)

        self.assertTrue(valid.isAccepted())
        self.assertEqual(self.window.source_image.size, (640, 800))

    def test_spec_spacing_margin_and_cut_lines_refresh_layout_immediately(self) -> None:
        self.assertTrue(self.load_portrait())

        self.window.spec_combo.setCurrentText("英语四六级")
        self.app.processEvents()
        self.assertEqual(self.window.count_label.text(), "共 56 张")

        self.window.spec_combo.setCurrentText("一寸")
        self.window.gap_spin.setValue(5.0)
        self.app.processEvents()
        self.assertEqual(self.window.count_label.text(), "共 10 张")

        self.window.gap_spin.setValue(1.0)
        self.window.margin_spin.setValue(5.0)
        self.app.processEvents()
        self.assertEqual(self.window.count_label.text(), "共 10 张")

        previous_pixmap_key = self.window.sheet_preview.pixmap().cacheKey()
        self.window.cut_lines_check.setChecked(False)
        self.app.processEvents()
        self.assertNotEqual(
            self.window.sheet_preview.pixmap().cacheKey(),
            previous_pixmap_key,
        )

    def test_crop_box_resets_to_new_automatic_geometry_on_spec_change(self) -> None:
        self.assertFalse(self.window.reset_crop_button.isEnabled())
        self.assertTrue(self.load_portrait())
        self.assertTrue(self.window.reset_crop_button.isEnabled())
        original_auto = self.window.crop_view.crop_box

        crop_rect = self.window.crop_view._crop_rect_widget()
        start = crop_rect.center().toPoint()
        end = (crop_rect.center() + QPointF(12, 12)).toPoint()
        QTest.mousePress(
            self.window.crop_view,
            Qt.MouseButton.LeftButton,
            pos=start,
        )
        QTest.mouseMove(self.window.crop_view, end)
        QTest.mouseRelease(
            self.window.crop_view,
            Qt.MouseButton.LeftButton,
            pos=end,
        )
        self.app.processEvents()
        self.assertNotEqual(self.window.crop_view.crop_box, original_auto)

        self.window.reset_crop_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.crop_view.crop_box, original_auto)

        self.window.spec_combo.setCurrentText("英语四六级")
        self.app.processEvents()
        expected = calculate_crop_box(
            self.face,
            1000,
            1200,
            TargetSize(12, 16),
        ).box
        self.assertEqual(self.window.crop_view.crop_box, expected)
        self.assertAlmostEqual(
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height,
            12 / 16,
        )

    def test_original_background_crop_changes_refresh_immediately_with_core_warning(self) -> None:
        self.assertTrue(self.load_portrait())
        initial_preview_key = self.window.sheet_preview.pixmap().cacheKey()
        boxes = (
            CropBox(210, 210, 610, 770),
            CropBox(220, 220, 620, 780),
            CropBox(230, 230, 430, 510),
        )

        with patch("ui.matting_worker.extract_foreground") as extract_foreground:
            for box in boxes:
                self.window.crop_view.cropBoxChanged.emit(box)
                self.app.processEvents()

        self.assertEqual(self.window.cropped_original.size, (200, 280))
        self.assertNotEqual(
            self.window.sheet_preview.pixmap().cacheKey(),
            initial_preview_key,
        )
        self.assertIn("裁剪区域像素不足", self.window.status_label.text())
        extract_foreground.assert_not_called()

    def test_original_drag_uses_fast_sheet_preview_then_restores_full_quality(self) -> None:
        self.assertTrue(self.load_portrait())
        box = CropBox(210, 210, 610, 770)

        with patch("ui.main_window.compose_sheet", wraps=compose_sheet) as compose:
            self.window.crop_view.cropBoxChanged.emit(box)
            self.assertEqual(compose.call_count, 1)
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.BOX,
            )

            self.window.crop_view.interactionFinished.emit(box)
            self.assertEqual(compose.call_count, 2)
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.LANCZOS,
            )

    def test_colored_background_only_restarts_matting_after_crop_release(self) -> None:
        self.assertTrue(self.load_portrait())

        def transparent_foreground(image: Image.Image) -> Image.Image:
            return Image.new("RGBA", image.size, (0, 0, 0, 0))

        boxes = (
            CropBox(210, 210, 610, 770),
            CropBox(220, 220, 620, 780),
            CropBox(230, 230, 630, 790),
        )
        with patch(
            "ui.matting_worker.extract_foreground",
            side_effect=transparent_foreground,
        ) as extract_foreground:
            self.window.blue_background_radio.setChecked(True)
            self.wait_until(lambda: not self.window.progress_bar.isVisible())
            self.assertEqual(extract_foreground.call_count, 1)

            for box in boxes:
                self.window.crop_view.cropBoxChanged.emit(box)
                self.app.processEvents()
                self.assertEqual(extract_foreground.call_count, 1)
                self.assertEqual(
                    self.window.finished_photo.getpixel((0, 0)),
                    self.window.cropped_original.getpixel((0, 0)),
                )
                self.assertIn("松开", self.window.status_label.text())

            self.window.crop_view.interactionFinished.emit(boxes[-1])
            self.wait_until(lambda: extract_foreground.call_count == 2)
            self.wait_until(lambda: not self.window.progress_bar.isVisible())

        self.assertEqual(
            self.window.finished_photo.getpixel((0, 0)),
            (67, 142, 219),
        )

    def test_bad_file_and_missing_face_show_recoverable_status(self) -> None:
        bad_path = Path(self.temp_dir.name) / "broken.jpg"
        bad_path.write_text("not an image", encoding="utf-8")

        self.assertFalse(self.window.load_image(bad_path))
        self.assertIn("无法读取照片", self.window.status_label.text())

        with patch("ui.main_window.detect_face", return_value=None):
            self.assertFalse(self.window.load_image(self.image_path))

        self.assertIn("未检测到人脸", self.window.status_label.text())
        self.assertFalse(self.window.original_preview.pixmap().isNull())
        self.assertIsNotNone(self.window.crop_view.crop_box)
        self.assertFalse(self.window.crop_preview.pixmap().isNull())
        self.assertFalse(self.window.sheet_preview.pixmap().isNull())
        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertFalse(self.window.reset_crop_button.isEnabled())

    def test_background_worker_keeps_controls_responsive_and_reuses_alpha(self) -> None:
        self.assertTrue(self.load_portrait())
        started = threading.Event()
        release = threading.Event()

        def slow_extract(image: Image.Image) -> Image.Image:
            started.set()
            if not release.wait(3):
                raise TimeoutError("test did not release matting worker")
            return Image.new("RGBA", image.size, (0, 0, 0, 0))

        with patch(
            "ui.matting_worker.extract_foreground",
            side_effect=slow_extract,
        ) as extract_foreground:
            self.window.blue_background_radio.setChecked(True)
            self.wait_until(started.is_set)
            self.wait_until(self.window.progress_bar.isVisible)

            self.window.gap_spin.setValue(5.0)
            self.app.processEvents()
            self.assertEqual(self.window.count_label.text(), "共 10 张")
            self.assertTrue(self.window.progress_bar.isVisible())

            release.set()
            self.wait_until(lambda: not self.window.progress_bar.isVisible())
            self.assertEqual(extract_foreground.call_count, 1)
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                (67, 142, 219),
            )

            self.window.red_background_radio.setChecked(True)
            self.app.processEvents()
            self.assertEqual(extract_foreground.call_count, 1)
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                (255, 0, 0),
            )
            self.assertIn("发丝处留白边", self.window.warning_label.text())

            self.window.original_background_radio.setChecked(True)
            self.app.processEvents()
            self.assertEqual(extract_foreground.call_count, 1)
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                self.window.cropped_original.getpixel((0, 0)),
            )

    def test_repeated_spec_changes_only_process_latest_pending_crop(self) -> None:
        self.assertTrue(self.load_portrait())
        first_started = threading.Event()
        first_release = threading.Event()
        second_started = threading.Event()
        second_release = threading.Event()
        call_sizes: list[tuple[int, int]] = []

        def controlled_extract(image: Image.Image) -> Image.Image:
            call_sizes.append(image.size)
            if len(call_sizes) == 1:
                first_started.set()
                if not first_release.wait(3):
                    raise TimeoutError("test did not release first worker")
            else:
                second_started.set()
                if not second_release.wait(3):
                    raise TimeoutError("test did not release second worker")
            return Image.new("RGBA", image.size, (0, 0, 0, 0))

        with patch(
            "ui.matting_worker.extract_foreground",
            side_effect=controlled_extract,
        ):
            self.window.blue_background_radio.setChecked(True)
            self.wait_until(first_started.is_set)

            self.window.spec_combo.setCurrentText("三寸")
            self.window.spec_combo.setCurrentText("英语四六级")
            self.app.processEvents()
            self.assertEqual(self.window.count_label.text(), "共 56 张")

            first_release.set()
            self.wait_until(second_started.is_set)
            self.assertEqual(len(call_sizes), 2)
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                self.window.cropped_original.getpixel((0, 0)),
            )

            second_release.set()
            self.wait_until(lambda: not self.window.progress_bar.isVisible())
            self.assertEqual(len(call_sizes), 2)
            self.assertEqual(self.window.count_label.text(), "共 56 张")
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                (67, 142, 219),
            )

    def test_matting_failure_restores_original_background_with_retry_message(self) -> None:
        self.assertTrue(self.load_portrait())

        with patch(
            "ui.matting_worker.extract_foreground",
            side_effect=RuntimeError("model failed"),
        ):
            self.window.blue_background_radio.setChecked(True)
            self.wait_until(self.window.original_background_radio.isChecked)
            self.wait_until(lambda: not self.window.progress_bar.isVisible())

        self.assertIn("抠图失败", self.window.status_label.text())
        self.assertIn("重试", self.window.status_label.text())
        self.assertEqual(
            self.window.finished_photo.getpixel((0, 0)),
            self.window.cropped_original.getpixel((0, 0)),
        )

    def test_reset_button_restores_default_spacing_and_refreshes_layout(self) -> None:
        self.load_portrait()
        self.window.gap_spin.setValue(6.5)
        self.window.margin_spin.setValue(4.0)
        reduced_count = self.window.count_label.text()

        self.window.reset_spacing_button.click()

        self.assertEqual(self.window.gap_spin.value(), 1.0)
        self.assertEqual(self.window.margin_spin.value(), 1.0)
        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertNotEqual(self.window.count_label.text(), reduced_count)

    def test_clicking_empty_space_drops_spinbox_focus(self) -> None:
        self.load_portrait()
        parameters_panel = getattr(self.window, "parameters_panel", None)
        original_card = getattr(self.window, "original_card", None)
        self.assertIsNotNone(parameters_panel)
        self.assertIsNotNone(original_card)

        self.window.gap_spin.setFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(self.window.gap_spin.hasFocus())
        QTest.mouseClick(
            parameters_panel,
            Qt.MouseButton.LeftButton,
            pos=parameters_panel.rect().bottomRight() - QPoint(8, 8),
        )
        self.app.processEvents()
        self.assertFalse(self.window.gap_spin.hasFocus())

        self.window.margin_spin.setFocus(Qt.FocusReason.TabFocusReason)
        self.assertTrue(self.window.margin_spin.hasFocus())
        QTest.mouseClick(
            original_card,
            Qt.MouseButton.LeftButton,
            pos=original_card.rect().topRight() - QPoint(8, -8),
        )
        self.app.processEvents()
        self.assertFalse(self.window.margin_spin.hasFocus())

    def test_header_reserves_stage_three_actions_without_buttons(self) -> None:
        header = getattr(self.window, "header_panel", None)
        output_container = getattr(self.window, "output_actions_container", None)
        output_layout = getattr(self.window, "output_actions_layout", None)
        separator = getattr(self.window, "output_actions_separator", None)
        self.assertIsNotNone(header)
        self.assertIsNotNone(output_container)
        self.assertIsNotNone(output_layout)
        self.assertIsNotNone(separator)
        self.assertEqual(header.height(), 56)
        self.assertTrue(output_container.isVisible())
        self.assertGreaterEqual(output_container.width(), 240)
        self.assertEqual(output_layout.count(), 0)
        self.assertFalse(separator.isVisible())

        self.window.resize(1040, 680)
        self.app.processEvents()
        self.assertTrue(
            header.rect().contains(
                self.window.import_button.mapTo(
                    header,
                    self.window.import_button.rect().bottomRight(),
                )
            )
        )

    def test_darkroom_workspace_uses_fixed_parameters_and_weighted_previews(self) -> None:
        parameters_panel = getattr(self.window, "parameters_panel", None)
        self.assertIsNotNone(parameters_panel)
        right_column = getattr(self.window, "right_column", None)
        status_bar = getattr(self.window, "status_bar", None)
        self.assertIsNotNone(right_column)
        self.assertIsNotNone(status_bar)
        self.assertEqual(self.window.minimumWidth(), 1040)
        self.assertEqual(self.window.minimumHeight(), 680)

        self.window.resize(1040, 680)
        self.app.processEvents()

        self.assertEqual(parameters_panel.width(), 220)
        preview_ratio = self.window.original_card.width() / right_column.width()
        self.assertGreater(preview_ratio, 1.08)
        self.assertLess(preview_ratio, 1.22)
        self.assertLess(parameters_panel.x(), self.window.original_card.x())
        self.assertLess(self.window.original_card.x(), right_column.x())
        self.assertLess(self.window.crop_card.y(), self.window.sheet_card.y())
        self.assertLessEqual(
            abs(self.window.crop_card.height() - self.window.sheet_card.height()),
            2,
        )
        self.assertEqual(status_bar.height(), 28)
        self.assertIs(self.window.status_label.parentWidget(), status_bar)
        self.assertIs(self.window.progress_bar.parentWidget(), status_bar)

        vertically_ordered_controls = (
            self.window.spec_combo,
            self.window.original_background_radio,
            self.window.gap_spin,
            self.window.margin_spin,
            self.window.cut_lines_check,
            self.window.reset_spacing_button,
        )
        y_positions = []
        for control in vertically_ordered_controls:
            with self.subTest(control=control.accessibleName() or control.text()):
                top_left = control.mapTo(parameters_panel, QPoint(0, 0))
                bottom_right = control.mapTo(
                    parameters_panel,
                    control.rect().bottomRight(),
                )
                self.assertTrue(parameters_panel.rect().contains(top_left))
                self.assertTrue(parameters_panel.rect().contains(bottom_right))
                y_positions.append(top_left.y())
        self.assertEqual(y_positions, sorted(y_positions))

        radio_widths = [
            radio.width()
            for radio in (
                self.window.original_background_radio,
                self.window.white_background_radio,
                self.window.blue_background_radio,
                self.window.red_background_radio,
            )
        ]
        self.assertLessEqual(max(radio_widths) - min(radio_widths), 1)

    def test_sheet_count_uses_visual_labels_without_changing_count_contract(self) -> None:
        self.assertTrue(self.load_portrait())

        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertTrue(self.window.count_label.isHidden())
        self.assertEqual(self.window.count_number_label.text(), "12")
        self.assertEqual(self.window.count_unit_label.text(), "张")
        self.assertEqual(self.window.sheet_preview.objectName(), "paperPreview")

        shadow = self.window.sheet_preview.graphicsEffect()
        self.assertIsInstance(shadow, QGraphicsDropShadowEffect)
        self.assertEqual(shadow.blurRadius(), 18.0)
        self.assertEqual(shadow.offset().x(), 0.0)
        self.assertEqual(shadow.offset().y(), 3.0)
        self.assertAlmostEqual(shadow.color().alphaF(), 0.45, places=2)



if __name__ == "__main__":
    unittest.main()
