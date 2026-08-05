import json
from pathlib import Path
import unittest

from core.crop import FaceGeometry, Point, TargetSize, calculate_crop_box


class CropGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs_path = Path(__file__).resolve().parents[1] / "specs.json"
        cls.specs = json.loads(specs_path.read_text(encoding="utf-8"))

    def test_all_specs_satisfy_geometry_constraints(self) -> None:
        face = FaceGeometry(
            head_top=Point(1000, 300),
            chin=Point(1000, 960),
            eyes_center=Point(1000, 650),
            face_axis_x=1000,
        )

        for name, spec in self.specs.items():
            with self.subTest(name=name):
                target = TargetSize(spec["width_mm"], spec["height_mm"])
                result = calculate_crop_box(face, 2200, 1600, target)
                box = result.box

                self.assertAlmostEqual(
                    box.width / box.height,
                    target.width_mm / target.height_mm,
                )
                self.assertGreaterEqual(result.headroom_ratio, 0.07)
                self.assertLessEqual(result.headroom_ratio, 0.12)
                self.assertGreaterEqual(result.head_height_ratio, 0.60)
                self.assertLessEqual(result.head_height_ratio, 0.72)
                self.assertGreaterEqual(result.eye_line_ratio, 0.43)
                self.assertLessEqual(result.eye_line_ratio, 0.47)
                self.assertLessEqual(result.axis_offset_ratio, 0.01)
                self.assertFalse(result.insufficient_space)
                self.assertFalse(result.insufficient_resolution)
                self.assertEqual(result.constraint_violations, ())

    def test_reports_headroom_conflict_without_moving_eye_line(self) -> None:
        face = FaceGeometry(
            head_top=Point(1000, 300),
            chin=Point(1000, 960),
            eyes_center=Point(1000, 600),
            face_axis_x=1000,
        )

        result = calculate_crop_box(face, 2200, 1600, TargetSize(25, 35))

        self.assertAlmostEqual(result.head_height_ratio, 0.66)
        self.assertAlmostEqual(result.eye_line_ratio, 0.45)
        self.assertGreater(result.headroom_ratio, 0.12)
        self.assertEqual(result.constraint_violations, ("headroom",))

    def test_marks_space_shortage_independently(self) -> None:
        face = FaceGeometry(
            head_top=Point(1000, 300),
            chin=Point(1000, 960),
            eyes_center=Point(1000, 650),
            face_axis_x=1000,
        )

        result = calculate_crop_box(face, 2200, 1100, TargetSize(25, 35))

        self.assertTrue(result.insufficient_space)
        self.assertFalse(result.insufficient_resolution)
        self.assertGreaterEqual(result.box.left, 0)
        self.assertGreaterEqual(result.box.top, 0)
        self.assertLessEqual(result.box.right, 2200)
        self.assertLessEqual(result.box.bottom, 1100)
        self.assertAlmostEqual(result.box.width / result.box.height, 25 / 35)

    def test_marks_resolution_shortage_independently(self) -> None:
        face = FaceGeometry(
            head_top=Point(500, 200),
            chin=Point(500, 398),
            eyes_center=Point(500, 305),
            face_axis_x=500,
        )

        result = calculate_crop_box(face, 1000, 1000, TargetSize(25, 35))

        self.assertFalse(result.insufficient_space)
        self.assertTrue(result.insufficient_resolution)
        self.assertEqual(result.constraint_violations, ())


if __name__ == "__main__":
    unittest.main()
