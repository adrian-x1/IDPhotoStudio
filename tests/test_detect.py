import importlib.util
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class FaceDetectionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            name
            for name in ("cv2", "mediapipe", "numpy")
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            raise unittest.SkipTest("missing integration dependencies: " + ", ".join(missing))

        import cv2
        import numpy as np

        from core.crop import TargetSize, calculate_crop_box
        from core.detect import _resolve_model_path, detect_face

        cls.cv2 = cv2
        cls.np = np
        cls.TargetSize = TargetSize
        cls.calculate_crop_box = staticmethod(calculate_crop_box)
        cls.detect_face = staticmethod(detect_face)
        cls.resolve_model_path = staticmethod(_resolve_model_path)

    def test_model_path_uses_pyinstaller_bundle_root(self) -> None:
        with TemporaryDirectory() as bundle_root:
            with patch.object(sys, "_MEIPASS", bundle_root, create=True):
                model_path = self.resolve_model_path()

        self.assertEqual(
            model_path,
            Path(bundle_root) / "assets" / "models" / "blaze_face_short_range.tflite",
        )

    def test_blank_image_returns_none(self) -> None:
        blank_rgb = self.np.zeros((480, 640, 3), dtype=self.np.uint8)

        self.assertIsNone(self.detect_face(blank_rgb))

    def test_three_private_samples_detect_and_crop_without_overflow(self) -> None:
        samples_dir = Path(__file__).resolve().parents[1] / "samples"
        sample_paths = sorted(samples_dir.glob("*.jpg"))
        self.assertEqual(len(sample_paths), 3)

        for sample_path in sample_paths:
            with self.subTest(sample=sample_path.name):
                encoded = self.np.fromfile(str(sample_path), dtype=self.np.uint8)
                bgr_image = self.cv2.imdecode(encoded, self.cv2.IMREAD_COLOR)
                self.assertIsNotNone(bgr_image)
                rgb_image = self.cv2.cvtColor(bgr_image, self.cv2.COLOR_BGR2RGB)
                image_height, image_width = rgb_image.shape[:2]

                face = self.detect_face(rgb_image)

                self.assertIsNotNone(face)
                self.assertTrue(math.isfinite(face.bbox_width))
                self.assertGreater(face.bbox_width, 0.0)
                self.assertTrue(math.isfinite(face.eyes_center.x))
                self.assertTrue(math.isfinite(face.eyes_center.y))
                self.assertGreaterEqual(face.eyes_center.x, 0.0)
                self.assertLessEqual(face.eyes_center.x, image_width)
                self.assertGreaterEqual(face.eyes_center.y, 0.0)
                self.assertLessEqual(face.eyes_center.y, image_height)

                result = self.calculate_crop_box(
                    face,
                    image_width,
                    image_height,
                    self.TargetSize(25, 35),
                )
                self.assertFalse(result.insufficient_space)
                self.assertGreaterEqual(result.box.left, 0.0)
                self.assertGreaterEqual(result.box.top, 0.0)
                self.assertLessEqual(result.box.right, image_width)
                self.assertLessEqual(result.box.bottom, image_height)


if __name__ == "__main__":
    unittest.main()
