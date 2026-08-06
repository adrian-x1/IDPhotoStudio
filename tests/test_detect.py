import importlib.util
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
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

        from core import detect as detect_module
        from core.crop import TargetSize, calculate_crop_box
        from core.detect import (
            _candidate_from_landmarks,
            _resolve_model_path,
            _select_largest_face,
            detect_face,
        )

        cls.cv2 = cv2
        cls.np = np
        cls.detect_module = detect_module
        cls.TargetSize = TargetSize
        cls.calculate_crop_box = staticmethod(calculate_crop_box)
        cls.detect_face = staticmethod(detect_face)
        cls.candidate_from_landmarks = staticmethod(_candidate_from_landmarks)
        cls.select_largest_face = staticmethod(_select_largest_face)
        cls.resolve_model_path = staticmethod(_resolve_model_path)

    class FakeLandmarker:
        def __init__(self) -> None:
            self.detect_calls = 0
            self.active_calls = 0
            self.maximum_active_calls = 0
            self.state_lock = threading.Lock()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def detect(self, _image):
            with self.state_lock:
                self.detect_calls += 1
                self.active_calls += 1
                self.maximum_active_calls = max(
                    self.maximum_active_calls,
                    self.active_calls,
                )
            time.sleep(0.05)
            with self.state_lock:
                self.active_calls -= 1
            return SimpleNamespace(face_landmarks=[])

    @staticmethod
    def landmarks(scale: float = 1.0):
        points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]

        def set_point(index: int, x: float, y: float) -> None:
            points[index] = SimpleNamespace(
                x=0.5 + (x - 0.5) * scale,
                y=0.5 + (y - 0.5) * scale,
            )

        set_point(10, 0.5, 0.2)
        set_point(152, 0.5, 0.8)
        set_point(33, 0.3, 0.4)
        set_point(263, 0.7, 0.4)
        for index, x in zip(range(468, 473), (0.38, 0.39, 0.40, 0.41, 0.42)):
            set_point(index, x, 0.45)
        for index, x in zip(range(473, 478), (0.58, 0.59, 0.60, 0.61, 0.62)):
            set_point(index, x, 0.45)
        return points

    def test_landmarks_produce_absolute_iris_geometry_and_euclidean_face_height(self) -> None:
        candidate = self.candidate_from_landmarks(
            self.landmarks(),
            image_width=1000,
            image_height=500,
        )

        self.assertIsNotNone(candidate)
        face = candidate.geometry
        self.assertEqual(face.forehead.x, 500.0)
        self.assertEqual(face.forehead.y, 100.0)
        self.assertEqual(face.chin.x, 500.0)
        self.assertEqual(face.chin.y, 400.0)
        self.assertAlmostEqual(face.face_height, 300.0)
        self.assertAlmostEqual(face.eyes_center.x, 500.0)
        self.assertAlmostEqual(face.eyes_center.y, 225.0)
        self.assertAlmostEqual(face.roll_degrees, 0.0)
        self.assertGreater(face.bbox_width, 0.0)

    def test_face_height_is_rotation_invariant(self) -> None:
        landmarks = self.landmarks()
        before = self.candidate_from_landmarks(landmarks, 1000, 1000)
        angle = math.radians(10.0)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        rotated = []
        for point in landmarks:
            x = point.x - 0.5
            y = point.y - 0.5
            rotated.append(
                SimpleNamespace(
                    x=0.5 + x * cosine - y * sine,
                    y=0.5 + x * sine + y * cosine,
                )
            )
        after = self.candidate_from_landmarks(rotated, 1000, 1000)

        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertAlmostEqual(after.geometry.face_height, before.geometry.face_height)
        self.assertAlmostEqual(after.geometry.roll_degrees, 10.0)

    def test_multiple_faces_select_largest_landmark_envelope(self) -> None:
        result = self.select_largest_face(
            [self.landmarks(scale=0.5), self.landmarks(scale=1.0)],
            image_width=1000,
            image_height=1000,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.face_count, 2)
        self.assertAlmostEqual(result.geometry.face_height, 600.0)

    def test_model_path_uses_pyinstaller_bundle_root(self) -> None:
        with TemporaryDirectory() as bundle_root:
            with patch.object(sys, "_MEIPASS", bundle_root, create=True):
                model_path = self.resolve_model_path()

        self.assertEqual(
            model_path,
            Path(bundle_root) / "assets" / "models" / "face_landmarker.task",
        )

    def test_blank_image_returns_none(self) -> None:
        blank_rgb = self.np.zeros((480, 640, 3), dtype=self.np.uint8)

        self.assertIsNone(self.detect_face(blank_rgb))

    def test_landmarker_instance_is_created_once_and_reused(self) -> None:
        fake = self.FakeLandmarker()
        image = self.np.zeros((2, 2, 3), dtype=self.np.uint8)

        with (
            patch.object(self.detect_module, "_landmarker", None, create=True),
            patch.object(
                self.detect_module.FaceLandmarker,
                "create_from_options",
                return_value=fake,
            ) as create,
        ):
            self.detect_face(image)
            self.detect_face(image)

        self.assertEqual(create.call_count, 1)
        self.assertEqual(fake.detect_calls, 2)

    def test_shared_landmarker_calls_are_serialized(self) -> None:
        fake = self.FakeLandmarker()
        image = self.np.zeros((2, 2, 3), dtype=self.np.uint8)
        errors = []

        def run_detection() -> None:
            try:
                self.detect_face(image)
            except Exception as error:  # pragma: no cover - assertion aid
                errors.append(error)

        with (
            patch.object(self.detect_module, "_landmarker", None, create=True),
            patch.object(
                self.detect_module.FaceLandmarker,
                "create_from_options",
                return_value=fake,
            ),
        ):
            workers = [threading.Thread(target=run_detection) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()

        self.assertEqual(errors, [])
        self.assertEqual(fake.detect_calls, 2)
        self.assertEqual(fake.maximum_active_calls, 1)

    def test_private_samples_detect_and_crop_without_overflow(self) -> None:
        samples_dir = Path(__file__).resolve().parents[1] / "samples"
        sample_paths = sorted(samples_dir.glob("*.jpg"))
        self.assertGreaterEqual(len(sample_paths), 3)

        for sample_path in sample_paths:
            with self.subTest(sample=sample_path.name):
                encoded = self.np.fromfile(str(sample_path), dtype=self.np.uint8)
                bgr_image = self.cv2.imdecode(encoded, self.cv2.IMREAD_COLOR)
                self.assertIsNotNone(bgr_image)
                rgb_image = self.cv2.cvtColor(bgr_image, self.cv2.COLOR_BGR2RGB)
                image_height, image_width = rgb_image.shape[:2]

                detection = self.detect_face(rgb_image)

                self.assertIsNotNone(detection)
                face = detection.geometry
                self.assertEqual(detection.face_count, 1)
                self.assertTrue(math.isfinite(face.bbox_width))
                self.assertGreater(face.bbox_width, 0.0)
                self.assertTrue(math.isfinite(face.face_height))
                self.assertGreater(face.face_height, 0.0)
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
