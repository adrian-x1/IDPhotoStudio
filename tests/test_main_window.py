import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Widget sizes are derived from font metrics, so pixel-exact assertions only
# hold where the Chinese UI fonts are installed.  CI runners lack them and
# report sizes that differ by a few pixels, so those checks run locally only.
FONT_SENSITIVE = unittest.skipIf(
    os.environ.get("CI") == "true",
    "pixel-exact widget sizes depend on locally installed Chinese fonts",
)

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QMenu,
    QRadioButton,
    QStyle,
    QStyleOptionButton,
    QToolButton,
)

from core.crop import (
    CropBox,
    FaceGeometry,
    Point,
    TargetSize,
    calculate_crop_box,
)
from core.detect import FaceDetectionResult
from core.layout import CUSTOM_SIZE_MAX_MM, CUSTOM_SIZE_MIN_MM, compose_sheet
from ui.main_window import (
    CUSTOM_SIZE_ENTRY_MAX_MM,
    CUSTOM_SIZE_PLACEHOLDER,
    CUSTOM_SPEC_LABEL,
    IMAGE_FILE_FILTER,
    JPEG_FILE_FILTER,
    PDF_FILE_FILTER,
    PNG_FILE_FILTER,
    SUPPORTED_IMAGE_SUFFIXES,
    MainWindow,
)
from ui.printing import PrintOutcome


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
            chin=Point(500.0, 700.0),
            forehead=Point(500.0, 300.0),
            eyes_center=Point(500.0, 500.0),
            roll_degrees=0.0,
            face_height=400.0,
        )
        self.detection = FaceDetectionResult(self.face, 1)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def load_portrait(self) -> bool:
        with patch("ui.main_window.detect_face", return_value=self.detection):
            return self.window.load_image(self.image_path)

    def select_custom_spec(self) -> None:
        self.window.spec_combo.setCurrentText(CUSTOM_SPEC_LABEL)
        self.app.processEvents()

    def commit_custom_size(self, spinbox, value: float) -> None:
        spinbox.setValue(value)
        spinbox.editingFinished.emit()
        self.app.processEvents()

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

    @FONT_SENSITIVE
    def test_rotation_controls_are_accessible_segmented_pairs(self) -> None:
        left_button = getattr(self.window, "rotate_photo_left_button", None)
        right_button = getattr(self.window, "rotate_photo_right_button", None)
        portrait_radio = getattr(self.window, "portrait_crop_radio", None)
        landscape_radio = getattr(self.window, "landscape_crop_radio", None)

        self.assertIsNotNone(left_button)
        self.assertIsNotNone(right_button)
        self.assertIsInstance(self.window.crop_orientation_group, QButtonGroup)
        self.assertTrue(self.window.crop_orientation_group.exclusive())
        self.assertIsInstance(portrait_radio, QRadioButton)
        self.assertIsInstance(landscape_radio, QRadioButton)
        self.assertEqual(left_button.text(), "")
        self.assertEqual(right_button.text(), "")
        self.assertFalse(left_button.icon().isNull())
        self.assertFalse(right_button.icon().isNull())
        self.assertEqual(portrait_radio.text(), "竖版")
        self.assertEqual(landscape_radio.text(), "横版")
        self.assertEqual(left_button.accessibleName(), "向左旋转照片 90 度")
        self.assertEqual(right_button.accessibleName(), "向右旋转照片 90 度")
        self.assertEqual(portrait_radio.accessibleName(), "竖版裁剪框")
        self.assertEqual(landscape_radio.accessibleName(), "横版裁剪框")
        self.assertIn("裁剪框方向不变", left_button.toolTip())
        self.assertIn("裁剪框方向不变", right_button.toolTip())
        self.assertIn("照片方向不变", portrait_radio.toolTip())
        self.assertIn("不改变 6 寸相纸排版", landscape_radio.toolTip())
        self.assertTrue(
            self.window.photo_rotation_control.property("segmentedControl")
        )
        self.assertTrue(
            self.window.crop_orientation_control.property("segmentedControl")
        )
        self.assertTrue(
            self.window.photo_rotation_divider.property("segmentDivider")
        )
        self.assertTrue(
            self.window.crop_orientation_divider.property("segmentDivider")
        )
        self.assertEqual(self.window.photo_rotation_control.layout().spacing(), 0)
        self.assertEqual(self.window.crop_orientation_control.layout().spacing(), 0)
        self.assertTrue(portrait_radio.isChecked())
        self.assertFalse(landscape_radio.isChecked())
        for radio in (portrait_radio, landscape_radio):
            with self.subTest(label=radio.text()):
                self.assertGreaterEqual(
                    radio.width(),
                    radio.sizeHint().width(),
                    "横竖版按钮必须完整容纳文字和内边距",
                )
        self.assertGreaterEqual(
            self.window.reset_crop_button.width(),
            self.window.reset_crop_button.sizeHint().width(),
            "重置按钮必须完整容纳文字和内边距",
        )
        for control in (
            left_button,
            right_button,
            portrait_radio,
            landscape_radio,
        ):
            with self.subTest(control=control.accessibleName()):
                self.assertTrue(control.property("segmentItem"))
                self.assertFalse(control.isEnabled())

    def test_colored_background_segments_show_only_centered_accessible_dots(self) -> None:
        colored_radios = (
            (self.window.white_background_radio, "白底"),
            (self.window.blue_background_radio, "蓝底"),
            (self.window.red_background_radio, "红底"),
        )

        for radio, accessible_name in colored_radios:
            with self.subTest(radio=radio.objectName()):
                self.assertEqual(radio.text(), "")
                self.assertEqual(radio.accessibleName(), accessible_name)
                option = QStyleOptionButton()
                radio.initStyleOption(option)
                indicator = radio.style().subElementRect(
                    QStyle.SubElement.SE_RadioButtonIndicator,
                    option,
                    radio,
                )
                self.assertAlmostEqual(
                    indicator.center().x(),
                    radio.rect().center().x(),
                    delta=1,
                )
                self.assertAlmostEqual(
                    indicator.center().y(),
                    radio.rect().center().y(),
                    delta=1,
                )

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
            patch("ui.main_window.detect_face", return_value=self.detection),
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
        with patch("ui.main_window.detect_face", return_value=self.detection):
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

        with patch("ui.main_window.detect_face", return_value=self.detection):
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

    def test_custom_size_progressively_enables_crop_and_preserves_face(self) -> None:
        self.assertTrue(self.load_portrait())
        detected_face = self.window.face

        self.select_custom_spec()

        self.assertTrue(self.window.custom_size_row.isVisible())
        self.assertEqual(self.window.custom_width_spin.minimum(), 0.0)
        self.assertEqual(self.window.custom_width_spin.text(), "")
        self.assertEqual(
            self.window.custom_width_spin.lineEdit().placeholderText(),
            CUSTOM_SIZE_PLACEHOLDER,
        )
        self.assertIsNone(self.window.crop_view.crop_box)
        self.assertIs(self.window.face, detected_face)
        self.assertIsNone(self.window.cropped_original)
        self.assertIsNone(self.window.finished_photo)
        self.assertIsNone(self.window.sheet_image)
        self.assertFalse(self.window.export_button.isEnabled())
        self.assertFalse(self.window.print_button.isEnabled())

        self.commit_custom_size(self.window.custom_width_spin, 35)
        self.assertEqual(self.window._custom_width_mm, 35)
        self.assertIsNone(self.window._custom_height_mm)
        self.assertIsNone(self.window.crop_view.crop_box)
        self.assertIs(self.window.face, detected_face)

        self.commit_custom_size(self.window.custom_height_spin, 50)
        expected = calculate_crop_box(
            self.face,
            self.window.source_image.width,
            self.window.source_image.height,
            TargetSize(35, 50),
        ).box
        self.assertEqual(self.window.crop_view.crop_box, expected)
        self.assertIsNotNone(self.window.finished_photo)
        self.assertIsNotNone(self.window.sheet_image)
        self.assertTrue(self.window.export_button.isEnabled())
        self.assertTrue(self.window.print_button.isEnabled())

    def test_custom_size_commits_only_on_editing_finished_or_focus_loss(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.commit_custom_size(self.window.custom_width_spin, 35)
        self.commit_custom_size(self.window.custom_height_spin, 50)
        original_box = self.window.crop_view.crop_box

        self.window.custom_width_spin.setValue(40)
        self.app.processEvents()
        self.assertEqual(self.window._custom_width_mm, 35)
        self.assertEqual(self.window.crop_view.crop_box, original_box)

        self.window.custom_width_spin.editingFinished.emit()
        self.app.processEvents()
        committed_box = self.window.crop_view.crop_box
        self.assertEqual(self.window._custom_width_mm, 40)
        self.assertNotEqual(committed_box, original_box)

        self.window.custom_height_spin.setFocus()
        self.app.processEvents()
        self.window.custom_height_spin.setValue(60)
        self.assertEqual(self.window._custom_height_mm, 50)
        self.assertEqual(self.window.crop_view.crop_box, committed_box)
        self.window.custom_height_spin.clearFocus()
        self.app.processEvents()
        self.assertEqual(self.window._custom_height_mm, 60)
        self.assertNotEqual(self.window.crop_view.crop_box, committed_box)

    def test_invalid_custom_size_keeps_last_committed_crop_until_corrected(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.commit_custom_size(self.window.custom_width_spin, 35)
        self.commit_custom_size(self.window.custom_height_spin, 50)
        valid_box = self.window.crop_view.crop_box

        self.commit_custom_size(self.window.custom_width_spin, 5)
        self.assertEqual(self.window._custom_width_mm, 35)
        self.assertEqual(self.window.crop_view.crop_box, valid_box)
        self.assertTrue(self.window.custom_width_spin.property("invalid"))
        self.assertEqual(
            self.window.warning_label.text(),
            "宽度需在 10 - 152 mm 之间",
        )
        self.assertEqual(self.window.warning_label.property("severity"), "error")

        self.commit_custom_size(self.window.custom_width_spin, 150)
        self.assertEqual(self.window._custom_width_mm, 150)
        self.assertFalse(self.window.custom_width_spin.property("invalid"))
        self.assertEqual(self.window._custom_size_error, "")
        self.assertNotEqual(self.window.crop_view.crop_box, valid_box)

        self.commit_custom_size(self.window.custom_height_spin, 0)
        self.assertIsNone(self.window._custom_height_mm)
        self.assertFalse(self.window.custom_height_spin.property("invalid"))
        self.assertIsNone(self.window.crop_view.crop_box)
        self.assertIsNone(self.window.finished_photo)
        self.assertIsNone(self.window.sheet_image)

    def test_custom_size_warning_priority_separates_layout_from_validation(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.commit_custom_size(self.window.custom_width_spin, 100)
        self.commit_custom_size(self.window.custom_height_spin, 150)
        valid_box = self.window.crop_view.crop_box

        with patch.object(self.window, "_request_matting"):
            self.window.red_background_radio.setChecked(True)
            self.app.processEvents()
        self.window.margin_spin.setValue(20)
        self.app.processEvents()
        self.assertEqual(self.window.crop_view.crop_box, valid_box)
        self.assertIsNotNone(self.window.finished_photo)
        self.assertIsNone(self.window.sheet_image)
        self.assertEqual(
            self.window.warning_label.text(),
            "当前排版无法容纳此规格，请减小边距",
        )

        self.commit_custom_size(self.window.custom_width_spin, 5)
        self.assertEqual(
            self.window.warning_label.text(),
            "宽度需在 10 - 152 mm 之间",
        )
        self.commit_custom_size(self.window.custom_width_spin, 100)
        self.assertEqual(
            self.window.warning_label.text(),
            "当前排版无法容纳此规格，请减小边距",
        )

        self.window.margin_spin.setValue(1)
        self.app.processEvents()
        self.assertIn("发丝处留白边", self.window.warning_label.text())
        self.assertEqual(self.window.warning_label.property("severity"), "")

    def test_custom_size_preserves_values_and_disables_orientation_only_in_mode(
        self,
    ) -> None:
        self.assertTrue(self.load_portrait())
        self.window.landscape_crop_radio.click()
        self.select_custom_spec()
        self.commit_custom_size(self.window.custom_width_spin, 35)
        self.commit_custom_size(self.window.custom_height_spin, 50)

        self.assertFalse(self.window.crop_orientation_control.isEnabled())
        self.assertFalse(self.window.portrait_crop_radio.isEnabled())
        self.assertFalse(self.window.landscape_crop_radio.isEnabled())
        self.assertEqual(
            self.window.crop_orientation_control.toolTip(),
            "自定义尺寸请直接调整宽高",
        )
        self.window.gap_spin.setValue(4)
        self.window.margin_spin.setValue(3)
        self.window.reset_spacing_button.click()
        self.app.processEvents()
        self.assertEqual(self.window._custom_width_mm, 35)
        self.assertEqual(self.window._custom_height_mm, 50)
        self.assertEqual(self.window.custom_width_spin.value(), 35)
        self.assertEqual(self.window.custom_height_spin.value(), 50)

        self.window.spec_combo.setCurrentText("一寸")
        self.app.processEvents()
        self.assertFalse(self.window.custom_size_row.isVisible())
        self.assertTrue(self.window.crop_orientation_control.isEnabled())
        self.assertTrue(self.window.landscape_crop_radio.isEnabled())
        self.assertTrue(self.window.landscape_crop_radio.isChecked())

    def test_custom_size_uses_dimensions_in_all_export_default_names(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.commit_custom_size(self.window.custom_width_spin, 35)
        self.commit_custom_size(self.window.custom_height_spin, 50)
        actions = (
            self.window.export_photo_jpeg_action,
            self.window.export_photo_png_action,
            self.window.export_sheet_jpeg_action,
            self.window.export_sheet_png_action,
            self.window.export_sheet_pdf_action,
        )

        with patch(
            "ui.main_window.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ) as save_dialog:
            for action in actions:
                action.trigger()

        self.assertEqual(
            [dialog_call.args[2] for dialog_call in save_dialog.call_args_list],
            [
                "35x50mm.jpg",
                "35x50mm.png",
                "35x50mm_4R.jpg",
                "35x50mm_4R.png",
                "35x50mm_4R.pdf",
            ],
        )

    def type_into(self, spinbox, text: str) -> None:
        """Drive a spinbox the way a person does: click, type, press Enter."""
        line_edit = spinbox.lineEdit()
        QTest.mouseClick(
            line_edit,
            Qt.MouseButton.LeftButton,
            pos=QPoint(line_edit.width() // 2, line_edit.height() // 2),
        )
        self.app.processEvents()
        QTest.keyClicks(spinbox, text)
        QTest.keyClick(spinbox, Qt.Key.Key_Return)
        self.app.processEvents()

    def test_clicking_into_an_empty_custom_size_accepts_typed_digits(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()

        self.type_into(self.window.custom_width_spin, "99")

        self.assertEqual(self.window.custom_width_spin.value(), 99)
        self.assertEqual(self.window._custom_width_mm, 99)
        self.assertFalse(self.window.custom_width_spin.property("invalid"))
        self.assertEqual(self.window.warning_label.text(), "")

        self.type_into(self.window.custom_height_spin, "50")
        self.assertEqual(self.window._custom_height_mm, 50)
        self.assertIsNotNone(self.window.crop_view.crop_box)

    def test_clicking_into_a_filled_custom_size_replaces_the_old_number(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.type_into(self.window.custom_width_spin, "35")

        self.type_into(self.window.custom_width_spin, "60")

        self.assertEqual(self.window.custom_width_spin.value(), 60)
        self.assertEqual(self.window._custom_width_mm, 60)

    def test_typed_out_of_range_custom_size_is_reported_not_truncated(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        self.type_into(self.window.custom_width_spin, "35")
        self.type_into(self.window.custom_height_spin, "50")
        committed_box = self.window.crop_view.crop_box

        for typed, expected in (("160", 160), ("200", 200), ("1000", 1000)):
            with self.subTest(typed=typed):
                self.type_into(self.window.custom_width_spin, typed)
                self.assertEqual(self.window.custom_width_spin.value(), expected)
                self.assertEqual(self.window._custom_width_mm, 35)
                self.assertTrue(
                    self.window.custom_width_spin.property("invalid")
                )
                self.assertEqual(
                    self.window.warning_label.text(),
                    "宽度需在 10 - 152 mm 之间",
                )
                self.assertEqual(self.window.crop_view.crop_box, committed_box)

        self.type_into(self.window.custom_width_spin, "35")
        self.assertFalse(self.window.custom_width_spin.property("invalid"))
        self.assertEqual(self.window.warning_label.text(), "")

    def test_entry_range_never_rejects_a_keystroke_below_its_maximum(self) -> None:
        spinbox = self.window.custom_width_spin
        self.assertGreater(spinbox.maximum(), CUSTOM_SIZE_MAX_MM)
        self.assertEqual(spinbox.maximum(), CUSTOM_SIZE_ENTRY_MAX_MM)

        self.select_custom_spec()
        line_edit = spinbox.lineEdit()
        line_edit.selectAll()
        typed = ""
        for character in "200":
            QTest.keyClicks(spinbox, character)
            typed += character
            self.assertEqual(spinbox.lineEdit().text(), typed)

    def test_clearing_a_custom_size_returns_to_the_unfilled_state(self) -> None:
        self.assertTrue(self.load_portrait())
        detected_face = self.window.face
        self.select_custom_spec()
        self.type_into(self.window.custom_width_spin, "35")
        self.type_into(self.window.custom_height_spin, "50")
        self.assertIsNotNone(self.window.crop_view.crop_box)

        spinbox = self.window.custom_width_spin
        spinbox.lineEdit().selectAll()
        QTest.keyClick(spinbox, Qt.Key.Key_Backspace)
        QTest.keyClick(spinbox, Qt.Key.Key_Return)
        self.app.processEvents()

        self.assertEqual(spinbox.text(), "")
        self.assertIsNone(self.window._custom_width_mm)
        self.assertIsNone(self.window.crop_view.crop_box)
        self.assertFalse(spinbox.property("invalid"))
        self.assertIs(self.window.face, detected_face)
        self.assertFalse(self.window.export_button.isEnabled())

        self.type_into(spinbox, "40")
        self.assertEqual(self.window._custom_width_mm, 40)
        self.assertIsNotNone(self.window.crop_view.crop_box)

    def test_custom_size_arrows_stay_inside_the_valid_range(self) -> None:
        self.assertTrue(self.load_portrait())
        self.select_custom_spec()
        spinbox = self.window.custom_width_spin
        spinbox.setFocus()
        self.app.processEvents()

        spinbox.stepUp()
        self.assertEqual(spinbox.value(), CUSTOM_SIZE_MIN_MM)
        spinbox.clearFocus()
        self.app.processEvents()
        self.assertFalse(spinbox.property("invalid"))
        self.assertEqual(self.window.warning_label.text(), "")
        self.assertEqual(self.window._custom_width_mm, CUSTOM_SIZE_MIN_MM)

        spinbox.stepDown()
        self.assertEqual(spinbox.value(), CUSTOM_SIZE_MIN_MM)

        spinbox.setValue(CUSTOM_SIZE_MAX_MM)
        spinbox.stepUp()
        self.assertEqual(spinbox.value(), CUSTOM_SIZE_MAX_MM)

    def test_photo_rotation_buttons_turn_both_directions_without_changing_crop(
        self,
    ) -> None:
        directional_path = Path(self.temp_dir.name) / "directional.png"
        directional = Image.new("RGB", (1000, 1200), (80, 100, 120))
        directional.paste((220, 40, 40), (0, 0, 500, 600))
        directional.paste((40, 180, 80), (500, 0, 1000, 600))
        directional.paste((40, 80, 220), (0, 600, 500, 1200))
        directional.save(directional_path)
        with patch("ui.main_window.detect_face", return_value=self.detection):
            self.assertTrue(self.window.load_image(directional_path))
        original_source = self.window.source_image.copy()
        original_ratio = (
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height
        )
        portrait_layout = self.window.sheet_layout
        portrait_sheet_size = self.window.sheet_image.size
        actions_and_sources = (
            (
                self.window.rotate_photo_left_button,
                original_source.transpose(Image.Transpose.ROTATE_90),
                3,
            ),
            (self.window.rotate_photo_right_button, original_source, 0),
            (
                self.window.rotate_photo_right_button,
                original_source.transpose(Image.Transpose.ROTATE_270),
                1,
            ),
            (
                self.window.rotate_photo_right_button,
                original_source.transpose(Image.Transpose.ROTATE_180),
                2,
            ),
            (
                self.window.rotate_photo_right_button,
                original_source.transpose(Image.Transpose.ROTATE_90),
                3,
            ),
            (self.window.rotate_photo_right_button, original_source, 0),
        )

        with patch(
            "ui.main_window.detect_face",
            return_value=self.detection,
        ) as detect:
            for button, expected_source, expected_quarters in actions_and_sources:
                button.click()
                self.app.processEvents()

                box = self.window.crop_view.crop_box
                self.assertEqual(self.window.source_image.size, expected_source.size)
                self.assertEqual(
                    self.window.source_image.tobytes(),
                    expected_source.tobytes(),
                )
                self.assertEqual(
                    (
                        self.window.crop_view.pixmap().width(),
                        self.window.crop_view.pixmap().height(),
                    ),
                    expected_source.size,
                )
                self.assertAlmostEqual(box.width / box.height, original_ratio)
                self.assertEqual(self.window.sheet_layout, portrait_layout)
                self.assertEqual(self.window.sheet_image.size, portrait_sheet_size)
                self.assertEqual(
                    self.window._photo_rotation_quarters,
                    expected_quarters,
                )

        self.assertEqual(detect.call_count, 6)
        self.assertEqual(
            [call.args[0].shape[:2] for call in detect.call_args_list],
            [
                (1000, 1200),
                (1200, 1000),
                (1000, 1200),
                (1200, 1000),
                (1000, 1200),
                (1200, 1000),
            ],
        )

    def test_crop_orientation_radios_switch_ratio_without_rotating_photo(self) -> None:
        self.assertTrue(self.load_portrait())
        source_bytes = self.window.source_image.tobytes()
        portrait_layout = self.window.sheet_layout
        portrait_sheet_size = self.window.sheet_image.size

        with patch("ui.main_window.detect_face") as detect:
            self.window.landscape_crop_radio.click()
            self.app.processEvents()
            self.assertEqual(self.window.source_image.tobytes(), source_bytes)
            self.assertFalse(self.window.portrait_crop_radio.isChecked())
            self.assertTrue(self.window.landscape_crop_radio.isChecked())
            self.assertAlmostEqual(
                self.window.crop_view.crop_box.width
                / self.window.crop_view.crop_box.height,
                35 / 25,
            )
            self.assertGreater(
                self.window.finished_photo.width,
                self.window.finished_photo.height,
            )
            self.window.portrait_crop_radio.click()
            self.app.processEvents()

        detect.assert_not_called()
        self.assertEqual(self.window.source_image.tobytes(), source_bytes)
        self.assertTrue(self.window.portrait_crop_radio.isChecked())
        self.assertFalse(self.window.landscape_crop_radio.isChecked())
        self.assertAlmostEqual(
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height,
            25 / 35,
        )
        self.assertEqual(self.window.sheet_layout, portrait_layout)
        self.assertEqual(self.window.sheet_image.size, portrait_sheet_size)

    def test_combined_rotations_keep_independent_state_and_sheet_layout(self) -> None:
        self.assertTrue(self.load_portrait())
        original_source = self.window.source_image.copy()
        original_layout = self.window.sheet_layout
        original_sheet_size = self.window.sheet_image.size

        with patch("ui.main_window.detect_face", return_value=self.detection):
            for _ in range(3):
                self.window.rotate_photo_right_button.click()
        self.window.landscape_crop_radio.click()
        self.app.processEvents()

        self.assertEqual(
            self.window.source_image.tobytes(),
            original_source.transpose(Image.Transpose.ROTATE_90).tobytes(),
        )
        self.assertAlmostEqual(
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height,
            35 / 25,
        )
        self.assertEqual(self.window.sheet_layout, original_layout)
        self.assertEqual(self.window.sheet_image.size, original_sheet_size)
        expected_sheet = compose_sheet(
            self.window.finished_photo.transpose(Image.Transpose.ROTATE_270),
            25,
            35,
            original_layout,
            gap=self.window.gap_spin.value(),
            draw_cut_lines=self.window.cut_lines_check.isChecked(),
        )
        self.assertEqual(self.window.sheet_image.tobytes(), expected_sheet.tobytes())

    def test_rotation_persists_across_specs_and_resets_for_a_new_image(self) -> None:
        self.assertTrue(self.load_portrait())
        with patch("ui.main_window.detect_face", return_value=self.detection):
            self.window.rotate_photo_right_button.click()
        self.window.landscape_crop_radio.click()

        self.window.spec_combo.setCurrentText("英语四六级")
        self.app.processEvents()
        self.assertEqual(self.window.source_image.size, (1200, 1000))
        self.assertEqual(self.window._photo_rotation_quarters, 1)
        self.assertTrue(self.window.landscape_crop_radio.isChecked())
        self.assertAlmostEqual(
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height,
            16 / 12,
        )

        self.assertTrue(self.load_portrait())
        self.assertEqual(self.window.source_image.size, (1000, 1200))
        self.assertEqual(self.window._photo_rotation_quarters, 0)
        self.assertTrue(self.window.portrait_crop_radio.isChecked())
        self.assertFalse(self.window.landscape_crop_radio.isChecked())
        self.assertAlmostEqual(
            self.window.crop_view.crop_box.width
            / self.window.crop_view.crop_box.height,
            12 / 16,
        )

    def test_missing_face_uses_centered_landscape_manual_crop(self) -> None:
        with patch("ui.main_window.detect_face", return_value=None):
            self.assertFalse(self.window.load_image(self.image_path))
            self.window.rotate_photo_right_button.click()
        self.window.landscape_crop_radio.click()
        self.app.processEvents()

        box = self.window.crop_view.crop_box
        self.assertAlmostEqual(box.width / box.height, 35 / 25)
        self.assertGreaterEqual(box.left, 0)
        self.assertGreaterEqual(box.top, 0)
        self.assertLessEqual(box.right, self.window.source_image.width)
        self.assertLessEqual(box.bottom, self.window.source_image.height)

    def test_reset_restores_original_photo_portrait_ai_crop(self) -> None:
        self.assertTrue(self.load_portrait())
        original_source = self.window.source_image.copy()
        self.window.spec_combo.setCurrentText("三寸")
        self.window.gap_spin.setValue(2.0)
        self.window.margin_spin.setValue(2.0)
        self.window.cut_lines_check.setChecked(False)
        with patch("ui.main_window.detect_face", return_value=self.detection) as detect:
            self.window.rotate_photo_right_button.click()
            self.window.landscape_crop_radio.click()
            automatic_box = self.window.crop_view.crop_box
            self.window.crop_view.cropBoxChanged.emit(
                CropBox(
                    automatic_box.left,
                    automatic_box.top + 10,
                    automatic_box.right,
                    automatic_box.bottom + 10,
                )
            )

            self.window.reset_crop_button.click()
            self.app.processEvents()

        expected_box = calculate_crop_box(
            self.face,
            original_source.width,
            original_source.height,
            TargetSize(55, 84),
        ).box
        self.assertEqual(self.window.source_image.tobytes(), original_source.tobytes())
        self.assertEqual(self.window._photo_rotation_quarters, 0)
        self.assertFalse(self.window._crop_orientation_landscape)
        self.assertTrue(self.window.portrait_crop_radio.isChecked())
        self.assertFalse(self.window.landscape_crop_radio.isChecked())
        self.assertEqual(self.window.crop_view.crop_box, expected_box)
        self.assertEqual(self.window.spec_combo.currentText(), "三寸")
        self.assertEqual(self.window.gap_spin.value(), 2.0)
        self.assertEqual(self.window.margin_spin.value(), 2.0)
        self.assertFalse(self.window.cut_lines_check.isChecked())
        self.assertEqual(detect.call_count, 2)

    def test_reset_discards_stale_matting_result(self) -> None:
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
            with patch("ui.main_window.detect_face", return_value=self.detection):
                self.window.rotate_photo_right_button.click()
                self.window.landscape_crop_radio.click()
            automatic_box = self.window.crop_view.crop_box
            self.window.crop_view.cropBoxChanged.emit(
                CropBox(
                    automatic_box.left,
                    automatic_box.top + 10,
                    automatic_box.right,
                    automatic_box.bottom + 10,
                )
            )
            self.window.blue_background_radio.setChecked(True)
            self.wait_until(first_started.is_set)

            with patch("ui.main_window.detect_face", return_value=self.detection):
                self.window.reset_crop_button.click()
            self.app.processEvents()
            first_release.set()
            self.wait_until(second_started.is_set)

            self.assertEqual(len(call_sizes), 2)
            self.assertEqual(self.window._photo_rotation_quarters, 0)
            self.assertTrue(self.window.portrait_crop_radio.isChecked())
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                self.window.cropped_original.getpixel((0, 0)),
            )

            second_release.set()
            self.wait_until(lambda: not self.window.progress_bar.isVisible())

        self.assertEqual(self.window.finished_photo.getpixel((0, 0)), (67, 142, 219))
        self.assertLess(
            self.window.finished_photo.width,
            self.window.finished_photo.height,
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

    def test_fractional_crop_uses_shared_integer_ratio_before_pillow_crop(self) -> None:
        self.assertTrue(self.load_portrait())
        box = CropBox(100.2, 100.2, 750.6, 1010.76)

        self.window._set_cropped_original(box)

        self.assertEqual(self.window.cropped_original.size, (650, 910))
        self.assertLess(abs(650 / 910 - 25 / 35), 1e-3)

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

    def test_spec_changes_update_immediately_with_fast_sheet_previews(self) -> None:
        self.assertTrue(self.load_portrait())
        initial_preview_key = self.window.sheet_preview.pixmap().cacheKey()

        with patch("ui.main_window.compose_sheet", wraps=compose_sheet) as compose:
            self.window.spec_combo.setCurrentText("三寸")
            self.assertEqual(self.window.count_label.text(), "共 2 张")
            self.assertNotEqual(
                self.window.sheet_preview.pixmap().cacheKey(),
                initial_preview_key,
            )
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.BOX,
            )

            self.window.spec_combo.setCurrentText("英语四六级")
            self.assertEqual(self.window.count_label.text(), "共 56 张")
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.BOX,
            )

    def test_rapid_spec_changes_refine_only_the_final_preview_once(self) -> None:
        self.assertTrue(self.load_portrait())

        with patch("ui.main_window.compose_sheet", wraps=compose_sheet) as compose:
            for spec_name in ("三寸", "二寸", "英语四六级"):
                self.window.spec_combo.setCurrentText(spec_name)

            self.assertEqual(compose.call_count, 3)
            self.assertTrue(
                all(
                    item.kwargs["resample"] == Image.Resampling.BOX
                    for item in compose.call_args_list
                )
            )
            QTest.qWait(300)
            self.app.processEvents()

        self.assertEqual(compose.call_count, 4)
        self.assertEqual(
            compose.call_args_list[-1].kwargs["resample"],
            Image.Resampling.LANCZOS,
        )
        self.assertEqual(self.window.spec_combo.currentText(), "英语四六级")
        self.assertEqual(self.window.count_label.text(), "共 56 张")

    def test_sheet_export_and_print_force_full_quality_during_fast_preview(self) -> None:
        self.assertTrue(self.load_portrait())
        export_path = str(Path(self.temp_dir.name) / "sheet.jpg")

        with (
            patch("ui.main_window.compose_sheet", wraps=compose_sheet) as compose,
            patch(
                "ui.main_window.QFileDialog.getSaveFileName",
                return_value=(export_path, ""),
            ),
            patch("ui.main_window.export_jpeg") as export_jpeg,
        ):
            self.window.spec_combo.setCurrentText("三寸")
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.BOX,
            )
            self.window.export_sheet_jpeg_action.trigger()
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.LANCZOS,
            )
            export_jpeg.assert_called_once_with(
                self.window.sheet_image,
                export_path,
            )

            self.window.spec_combo.setCurrentText("英语四六级")
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.BOX,
            )
            with patch(
                "ui.main_window.print_sheet",
                return_value=PrintOutcome.CANCELLED,
            ) as print_sheet:
                self.window.print_button.click()
            self.assertEqual(
                compose.call_args.kwargs["resample"],
                Image.Resampling.LANCZOS,
            )
            print_sheet.assert_called_once_with(
                self.window.sheet_image,
                self.window.sheet_layout,
                self.window,
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
        self.assertFalse(self.window.rotate_photo_left_button.isEnabled())
        self.assertFalse(self.window.rotate_photo_right_button.isEnabled())
        self.assertFalse(self.window.portrait_crop_radio.isEnabled())
        self.assertFalse(self.window.landscape_crop_radio.isEnabled())

        with patch("ui.main_window.detect_face", return_value=None):
            self.assertFalse(self.window.load_image(self.image_path))

        self.assertIn("未检测到人脸", self.window.status_label.text())
        self.assertFalse(self.window.original_preview.pixmap().isNull())
        self.assertIsNotNone(self.window.crop_view.crop_box)
        self.assertFalse(self.window.crop_preview.pixmap().isNull())
        self.assertFalse(self.window.sheet_preview.pixmap().isNull())
        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertFalse(self.window.reset_crop_button.isEnabled())
        self.assertTrue(self.window.rotate_photo_left_button.isEnabled())
        self.assertTrue(self.window.rotate_photo_right_button.isEnabled())
        self.assertTrue(self.window.portrait_crop_radio.isEnabled())
        self.assertTrue(self.window.landscape_crop_radio.isEnabled())

    def test_photo_rotation_detection_failure_uses_recoverable_error_state(
        self,
    ) -> None:
        self.assertTrue(self.load_portrait())

        with patch(
            "ui.main_window.detect_face",
            side_effect=RuntimeError("model unavailable"),
        ):
            self.window.rotate_photo_right_button.click()
        self.app.processEvents()

        self.assertEqual(self.window.source_image.size, (1200, 1000))
        self.assertEqual(
            (
                self.window.crop_view.pixmap().width(),
                self.window.crop_view.pixmap().height(),
            ),
            (1200, 1000),
        )
        self.assertIn("人脸检测失败", self.window.status_label.text())
        self.assertIsNone(self.window.crop_view.crop_box)
        self.assertIsNone(self.window.sheet_image)
        self.assertTrue(self.window.rotate_photo_left_button.isEnabled())
        self.assertTrue(self.window.rotate_photo_right_button.isEnabled())
        self.assertTrue(self.window.portrait_crop_radio.isEnabled())
        self.assertTrue(self.window.landscape_crop_radio.isEnabled())
        # Reset is the only way back from a failed rotation, so it must stay live.
        self.assertTrue(self.window.reset_crop_button.isEnabled())

    def test_reset_stays_available_when_rotation_hides_the_face(self) -> None:
        self.assertTrue(self.load_portrait())

        # A photo turned upside down usually defeats face detection, but the
        # user still has to be able to undo the rotation.
        with patch("ui.main_window.detect_face", return_value=None):
            self.window.rotate_photo_right_button.click()
            self.window.rotate_photo_right_button.click()
        self.app.processEvents()

        self.assertEqual(self.window._photo_rotation_quarters, 2)
        self.assertTrue(self.window.reset_crop_button.isEnabled())

        self.window.reset_crop_button.click()
        self.app.processEvents()

        self.assertEqual(self.window._photo_rotation_quarters, 0)
        self.assertEqual(
            self.window.source_image.size, self.window._original_source_image.size
        )

    def test_rotation_buttons_do_not_keep_a_selected_look_after_clicking(self) -> None:
        self.assertTrue(self.load_portrait())

        for button in (
            self.window.rotate_photo_left_button,
            self.window.rotate_photo_right_button,
        ):
            with self.subTest(button=button.accessibleName()):
                # Rotation is a one-shot action; unlike the orientation radios it
                # has no persistent on state, so it must not retain focus styling.
                self.assertFalse(button.isCheckable())
                self.assertEqual(
                    button.focusPolicy(), Qt.FocusPolicy.NoFocus
                )
                button.click()
                self.app.processEvents()
                self.assertFalse(button.hasFocus())

    def test_multiple_faces_show_non_blocking_largest_face_notice(self) -> None:
        detection = FaceDetectionResult(self.face, 2)

        with patch("ui.main_window.detect_face", return_value=detection):
            self.assertTrue(self.window.load_image(self.image_path))

        self.assertIn(
            "检测到多张人脸，已按最大的裁剪",
            self.window.status_label.text(),
        )
        self.assertIsNotNone(self.window.sheet_image)

    def test_roll_over_five_degrees_shows_non_blocking_notice(self) -> None:
        detection = FaceDetectionResult(
            replace(self.face, roll_degrees=-6.25),
            1,
        )

        with patch("ui.main_window.detect_face", return_value=detection):
            self.assertTrue(self.window.load_image(self.image_path))

        self.assertIn(
            "头部倾斜 6.2 度，建议重拍",
            self.window.status_label.text(),
        )
        self.assertIsNotNone(self.window.sheet_image)

    def test_small_face_shows_derived_resolution_notice_without_blocking(self) -> None:
        detection = FaceDetectionResult(
            replace(self.face, face_height=100.0),
            1,
        )

        with patch("ui.main_window.detect_face", return_value=detection):
            self.assertTrue(self.window.load_image(self.image_path))

        self.assertIn(
            "人脸太小，裁剪后像素不足",
            self.window.status_label.text(),
        )
        self.assertIsNotNone(self.window.sheet_image)

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

    def _assert_rotation_discards_stale_matting_result(
        self,
        button_name: str,
        *,
        expect_landscape: bool,
    ) -> None:
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

            if button_name.startswith("rotate_photo_"):
                with patch(
                    "ui.main_window.detect_face",
                    return_value=self.detection,
                ):
                    getattr(self.window, button_name).click()
            else:
                getattr(self.window, button_name).click()
            self.app.processEvents()
            first_release.set()
            self.wait_until(second_started.is_set)

            self.assertEqual(len(call_sizes), 2)
            self.assertLess(call_sizes[0][0], call_sizes[0][1])
            self.assertEqual(
                self.window.finished_photo.getpixel((0, 0)),
                self.window.cropped_original.getpixel((0, 0)),
            )

            second_release.set()
            self.wait_until(lambda: not self.window.progress_bar.isVisible())

        if expect_landscape:
            self.assertGreater(
                self.window.finished_photo.width,
                self.window.finished_photo.height,
            )
        else:
            self.assertLess(
                self.window.finished_photo.width,
                self.window.finished_photo.height,
            )
        self.assertEqual(self.window.finished_photo.getpixel((0, 0)), (67, 142, 219))

    def test_left_photo_rotation_discards_stale_matting_result(self) -> None:
        self._assert_rotation_discards_stale_matting_result(
            "rotate_photo_left_button",
            expect_landscape=False,
        )

    def test_right_photo_rotation_discards_stale_matting_result(self) -> None:
        self._assert_rotation_discards_stale_matting_result(
            "rotate_photo_right_button",
            expect_landscape=False,
        )

    def test_crop_orientation_change_discards_stale_matting_result(self) -> None:
        self._assert_rotation_discards_stale_matting_result(
            "landscape_crop_radio",
            expect_landscape=True,
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

    def test_clicking_empty_crop_view_opens_image_chooser(self) -> None:
        with patch(
            "ui.main_window.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as open_dialog:
            QTest.mouseClick(
                self.window.crop_view,
                Qt.MouseButton.LeftButton,
                pos=self.window.crop_view.rect().center(),
            )

        open_dialog.assert_called_once()

    def test_header_contains_restructured_export_menu_actions(self) -> None:
        header = getattr(self.window, "header_panel", None)
        separator = getattr(self.window, "header_separator", None)
        self.assertIsNotNone(header)
        self.assertIsNotNone(separator)
        self.assertEqual(header.height(), 56)
        self.assertEqual(header.layout().spacing(), 8)
        for removed_name in (
            "output_actions_container",
            "output_actions_layout",
            "output_actions_separator",
        ):
            self.assertFalse(hasattr(self.window, removed_name))
        title = header.findChild(QLabel, "appTitle")
        self.assertIsNotNone(title)
        self.assertEqual(title.text(), "证件照排版")
        self.assertIsNone(header.findChild(QLabel, "appSubtitle"))

        header_widgets = [
            header.layout().itemAt(index).widget()
            for index in range(header.layout().count())
            if header.layout().itemAt(index).widget() is not None
        ]
        self.assertEqual(
            header_widgets,
            [
                title,
                self.window.import_button,
                self.window.export_button,
                separator,
                self.window.print_button,
            ],
        )
        self.assertEqual(self.window.import_button.text(), "导入")
        self.assertEqual(self.window.export_button.text(), "导出")
        self.assertEqual(self.window.print_button.text(), "打印")
        self.assertIsNone(self.window.import_button.property("variant"))
        self.assertIsNone(self.window.export_button.property("variant"))
        self.assertEqual(self.window.print_button.property("variant"), "primary")
        for button in (
            self.window.import_button,
            self.window.export_button,
            self.window.print_button,
        ):
            self.assertEqual(button.minimumHeight(), 36)
        self.assertIsInstance(self.window.export_button, QToolButton)
        self.assertEqual(
            self.window.export_button.popupMode(),
            QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self.assertEqual(
            self.window.export_button.toolButtonStyle(),
            Qt.ToolButtonStyle.ToolButtonTextOnly,
        )
        self.assertIsInstance(self.window.export_button.menu(), QMenu)
        self.assertIsInstance(separator, QFrame)
        self.assertEqual(separator.contentsMargins().left(), 4)
        self.assertEqual(separator.contentsMargins().right(), 4)
        self.assertTrue(separator.isVisible())

        menu_actions = self.window.export_button.menu().actions()
        self.assertEqual(
            [action.text() for action in menu_actions],
            [
                "单张证件照",
                "导出 JPEG",
                "导出 PNG",
                "6 寸相纸",
                "导出 JPEG",
                "导出 PNG",
                "导出 PDF",
            ],
        )
        for section in (menu_actions[0], menu_actions[3]):
            self.assertFalse(section.isEnabled())
            self.assertFalse(section.isSeparator())

        expected_actions = [
            self.window.export_photo_jpeg_action,
            self.window.export_photo_png_action,
            self.window.export_sheet_jpeg_action,
            self.window.export_sheet_png_action,
            self.window.export_sheet_pdf_action,
        ]
        triggerable_actions = [
            action
            for action in self.window.export_button.menu().actions()
            if action in expected_actions
        ]
        self.assertEqual(triggerable_actions, expected_actions)
        self.assertEqual(
            [action.text() for action in triggerable_actions],
            ["导出 JPEG", "导出 PNG", "导出 JPEG", "导出 PNG", "导出 PDF"],
        )

    @FONT_SENSITIVE
    def test_header_action_buttons_use_equal_visual_size(self) -> None:
        buttons = (
            self.window.import_button,
            self.window.export_button,
            self.window.print_button,
        )
        layout_widgets = (
            self.window.import_button,
            self.window.export_button_container,
            self.window.print_button,
        )
        header_layout = self.window.header_panel.layout()

        self.assertEqual(
            [button.size() for button in buttons],
            [buttons[0].size()] * len(buttons),
        )
        self.assertTrue(
            all(
                next(
                    header_layout.itemAt(index)
                    for index in range(header_layout.count())
                    if header_layout.itemAt(index).widget() is button
                ).alignment()
                & Qt.AlignmentFlag.AlignVCenter
                for button in layout_widgets
            )
        )

    def test_cocoa_header_action_buttons_share_the_same_top_edge(self) -> None:
        if QApplication.platformName() != "cocoa":
            self.skipTest("macOS Cocoa layout regression")

        buttons = (
            self.window.import_button,
            self.window.export_button,
            self.window.print_button,
        )
        top_edges = [
            button.mapTo(self.window.header_panel, QPoint()).y()
            for button in buttons
        ]

        self.assertEqual(top_edges, [top_edges[0]] * len(buttons))

    def test_output_actions_follow_photo_and_sheet_data_independently(self) -> None:
        photo_actions = (
            self.window.export_photo_jpeg_action,
            self.window.export_photo_png_action,
        )
        sheet_actions = (
            self.window.export_sheet_jpeg_action,
            self.window.export_sheet_png_action,
            self.window.export_sheet_pdf_action,
        )
        self.assertTrue(all(not action.isEnabled() for action in photo_actions))
        self.assertTrue(all(not action.isEnabled() for action in sheet_actions))
        self.assertFalse(self.window.export_button.isEnabled())
        self.assertFalse(self.window.print_button.isEnabled())

        self.assertTrue(self.load_portrait())
        self.assertTrue(all(action.isEnabled() for action in photo_actions))
        self.assertTrue(all(action.isEnabled() for action in sheet_actions))
        self.assertTrue(self.window.export_button.isEnabled())
        self.assertTrue(self.window.print_button.isEnabled())

        self.window.margin_spin.setMaximum(100)
        self.window.margin_spin.setValue(100)
        self.app.processEvents()
        self.assertIsNotNone(self.window.finished_photo)
        self.assertIsNone(self.window.sheet_image)
        self.assertTrue(all(action.isEnabled() for action in photo_actions))
        self.assertTrue(all(not action.isEnabled() for action in sheet_actions))
        self.assertTrue(self.window.export_button.isEnabled())
        self.assertFalse(self.window.print_button.isEnabled())

    def test_export_actions_use_expected_names_filters_and_image_sources(self) -> None:
        self.assertTrue(self.load_portrait())
        paths = [
            str(Path(self.temp_dir.name) / name)
            for name in (
                "一寸.jpg",
                "一寸.png",
                "一寸_4R.jpg",
                "一寸_4R.png",
                "一寸_4R.pdf",
            )
        ]
        rendered_photo = Image.new("RGB", (295, 413), "white")
        target = self.window._current_target_size()
        actions = (
            self.window.export_photo_jpeg_action,
            self.window.export_photo_png_action,
            self.window.export_sheet_jpeg_action,
            self.window.export_sheet_png_action,
            self.window.export_sheet_pdf_action,
        )

        with (
            patch(
                "ui.main_window.QFileDialog.getSaveFileName",
                side_effect=[(path, "") for path in paths],
            ) as save_dialog,
            patch(
                "ui.main_window.render_photo",
                return_value=rendered_photo,
            ) as render_photo,
            patch("ui.main_window.export_jpeg") as export_jpeg,
            patch("ui.main_window.export_png") as export_png,
            patch("ui.main_window.export_pdf") as export_pdf,
        ):
            for action in actions:
                action.trigger()

        self.assertEqual(
            [dialog_call.args[2] for dialog_call in save_dialog.call_args_list],
            ["一寸.jpg", "一寸.png", "一寸_4R.jpg", "一寸_4R.png", "一寸_4R.pdf"],
        )
        self.assertEqual(
            [dialog_call.args[3] for dialog_call in save_dialog.call_args_list],
            [JPEG_FILE_FILTER, PNG_FILE_FILTER, JPEG_FILE_FILTER, PNG_FILE_FILTER, PDF_FILE_FILTER],
        )
        expected_render_call = call(
            self.window.finished_photo,
            target.width_mm,
            target.height_mm,
        )
        self.assertEqual(
            render_photo.call_args_list,
            [expected_render_call, expected_render_call],
        )
        self.assertEqual(
            export_jpeg.call_args_list,
            [call(rendered_photo, paths[0]), call(self.window.sheet_image, paths[2])],
        )
        self.assertEqual(
            export_png.call_args_list,
            [call(rendered_photo, paths[1]), call(self.window.sheet_image, paths[3])],
        )
        export_pdf.assert_called_once_with(self.window.sheet_image, paths[4])
        self.assertEqual(self.window.status_label.text(), f"相纸 PDF 已导出：{paths[4]}")

    def test_cancelled_export_actions_do_not_render_or_write(self) -> None:
        self.assertTrue(self.load_portrait())
        actions = (
            self.window.export_photo_jpeg_action,
            self.window.export_photo_png_action,
            self.window.export_sheet_jpeg_action,
            self.window.export_sheet_png_action,
            self.window.export_sheet_pdf_action,
        )

        with (
            patch(
                "ui.main_window.QFileDialog.getSaveFileName",
                return_value=("", ""),
            ),
            patch("ui.main_window.render_photo") as render_photo,
            patch("ui.main_window.export_jpeg") as export_jpeg,
            patch("ui.main_window.export_png") as export_png,
            patch("ui.main_window.export_pdf") as export_pdf,
        ):
            for action in actions:
                action.trigger()

        render_photo.assert_not_called()
        export_jpeg.assert_not_called()
        export_png.assert_not_called()
        export_pdf.assert_not_called()

    def test_export_io_failures_are_reported_in_the_status_bar(self) -> None:
        self.assertTrue(self.load_portrait())
        cases = (
            (self.window.export_photo_jpeg_action, "export_jpeg", PermissionError("photo jpg")),
            (self.window.export_photo_png_action, "export_png", IOError("photo png")),
            (self.window.export_sheet_jpeg_action, "export_jpeg", IOError("sheet jpg")),
            (self.window.export_sheet_png_action, "export_png", PermissionError("sheet png")),
            (self.window.export_sheet_pdf_action, "export_pdf", IOError("sheet pdf")),
        )

        for action, function_name, error in cases:
            with self.subTest(function=function_name):
                with (
                    patch(
                        "ui.main_window.QFileDialog.getSaveFileName",
                        return_value=(str(Path(self.temp_dir.name) / "output"), ""),
                    ),
                    patch(f"ui.main_window.{function_name}", side_effect=error),
                ):
                    action.trigger()
                self.assertIn("导出", self.window.status_label.text())
                self.assertIn(str(error), self.window.status_label.text())

    def test_print_outcomes_update_status_without_overwriting_cancel(self) -> None:
        self.assertTrue(self.load_portrait())

        with patch(
            "ui.main_window.print_sheet",
            return_value=PrintOutcome.NO_PRINTER,
        ):
            self.window.print_button.click()
        self.assertEqual(self.window.status_label.text(), "没有可用打印机")

        previous_status = self.window.status_label.text()
        with patch(
            "ui.main_window.print_sheet",
            return_value=PrintOutcome.CANCELLED,
        ):
            self.window.print_button.click()
        self.assertEqual(self.window.status_label.text(), previous_status)

        with patch(
            "ui.main_window.print_sheet",
            return_value=PrintOutcome.PRINTED,
        ):
            self.window.print_button.click()
        self.assertEqual(self.window.status_label.text(), "已发送到打印机")

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
