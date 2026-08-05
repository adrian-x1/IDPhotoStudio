import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
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

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def load_portrait(self) -> bool:
        with patch("ui.main_window.detect_face", return_value=self.face):
            return self.window.load_image(self.image_path)

    def test_default_original_background_loads_all_three_previews(self) -> None:
        self.assertEqual(self.window.spec_combo.currentText(), "一寸")
        self.assertTrue(self.window.original_background_radio.isChecked())
        self.assertEqual(self.window.gap_spin.value(), 1.0)
        self.assertEqual(self.window.margin_spin.value(), 1.0)
        self.assertTrue(self.window.cut_lines_check.isChecked())

        self.assertTrue(self.load_portrait())

        self.assertFalse(self.window.original_preview.pixmap().isNull())
        self.assertFalse(self.window.crop_preview.pixmap().isNull())
        self.assertFalse(self.window.sheet_preview.pixmap().isNull())
        self.assertEqual(self.window.count_label.text(), "共 12 张")
        self.assertEqual(self.window.status_label.text(), "保持原底，未执行抠图")

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


if __name__ == "__main__":
    unittest.main()
