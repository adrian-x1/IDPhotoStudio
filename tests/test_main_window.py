import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.crop import FaceGeometry, Point
from ui.main_window import MainWindow


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

    def test_bad_file_and_missing_face_show_recoverable_status(self) -> None:
        bad_path = Path(self.temp_dir.name) / "broken.jpg"
        bad_path.write_text("not an image", encoding="utf-8")

        self.assertFalse(self.window.load_image(bad_path))
        self.assertIn("无法读取照片", self.window.status_label.text())

        with patch("ui.main_window.detect_face", return_value=None):
            self.assertFalse(self.window.load_image(self.image_path))

        self.assertIn("未检测到人脸", self.window.status_label.text())
        self.assertFalse(self.window.original_preview.pixmap().isNull())
        self.assertTrue(self.window.crop_preview.pixmap().isNull())
        self.assertTrue(self.window.sheet_preview.pixmap().isNull())
        self.assertEqual(self.window.count_label.text(), "共 — 张")

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


if __name__ == "__main__":
    unittest.main()
