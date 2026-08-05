import importlib.util
import math
from pathlib import Path
import sys
import unittest


REQUIRES_PYTHON_311 = sys.version_info[:2] == (3, 11)


@unittest.skipUnless(REQUIRES_PYTHON_311, "requires Python 3.11")
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

        from core.detect import detect_face

        cls.cv2 = cv2
        cls.np = np
        cls.detect_face = staticmethod(detect_face)

    def test_blank_image_returns_none(self) -> None:
        blank_rgb = self.np.zeros((480, 640, 3), dtype=self.np.uint8)

        self.assertIsNone(self.detect_face(blank_rgb))

    def test_private_sample_images_return_ordered_finite_geometry(self) -> None:
        samples_dir = Path(__file__).resolve().parents[1] / "samples"
        sample_paths = sorted(samples_dir.glob("*.jpg"))
        if not sample_paths:
            self.skipTest("private sample images are not available")

        for sample_path in sample_paths:
            with self.subTest(sample=sample_path.name):
                encoded = self.np.fromfile(str(sample_path), dtype=self.np.uint8)
                bgr_image = self.cv2.imdecode(encoded, self.cv2.IMREAD_COLOR)
                self.assertIsNotNone(bgr_image)
                rgb_image = self.cv2.cvtColor(bgr_image, self.cv2.COLOR_BGR2RGB)

                face = self.detect_face(rgb_image)

                self.assertIsNotNone(face)
                coordinates = (
                    face.head_top.x,
                    face.head_top.y,
                    face.chin.x,
                    face.chin.y,
                    face.eyes_center.x,
                    face.eyes_center.y,
                    face.face_axis_x,
                )
                self.assertTrue(all(math.isfinite(value) for value in coordinates))
                self.assertLess(face.head_top.y, face.eyes_center.y)
                self.assertLess(face.eyes_center.y, face.chin.y)
                self.assertAlmostEqual(face.face_axis_x, face.eyes_center.x)


if __name__ == "__main__":
    unittest.main()
