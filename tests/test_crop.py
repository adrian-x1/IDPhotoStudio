import json
from pathlib import Path
import unittest

from core.crop import (
    EYE_LINE,
    K,
    LOWER_EDGE_LIFT_RATIO,
    FaceGeometry,
    Point,
    TargetSize,
    calculate_crop_box,
)


class CropGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs_path = Path(__file__).resolve().parents[1] / "specs.json"
        cls.specs = json.loads(specs_path.read_text(encoding="utf-8"))

    def test_all_specs_follow_empirical_geometry(self) -> None:
        face = FaceGeometry(
            bbox_width=1000.0,
            eyes_center=Point(2000.0, 1500.0),
        )

        for name, spec in self.specs.items():
            with self.subTest(name=name):
                target = TargetSize(spec["width_mm"], spec["height_mm"])
                result = calculate_crop_box(face, 4000, 4000, target)
                box = result.box
                expected_width = face.bbox_width * K
                expected_height = expected_width * target.height_mm / target.width_mm

                self.assertAlmostEqual(box.width, expected_width)
                self.assertAlmostEqual(box.height, expected_height)
                self.assertAlmostEqual((box.left + box.right) / 2, face.eyes_center.x)
                self.assertAlmostEqual(
                    (face.eyes_center.y - box.top) / box.height,
                    EYE_LINE + LOWER_EDGE_LIFT_RATIO,
                )
                self.assertFalse(result.insufficient_space)
                self.assertFalse(result.insufficient_resolution)

    def test_lower_edge_lift_is_adjustable_and_preserves_crop_ratio(self) -> None:
        face = FaceGeometry(
            bbox_width=1000.0,
            eyes_center=Point(2000.0, 1500.0),
        )
        target = TargetSize(25, 35)

        lifted = calculate_crop_box(face, 4000, 4000, target)
        unlifted = calculate_crop_box(
            face,
            4000,
            4000,
            target,
            lower_edge_lift_ratio=0.0,
        )

        expected_lift = lifted.box.height * LOWER_EDGE_LIFT_RATIO
        self.assertEqual(LOWER_EDGE_LIFT_RATIO, 0.05)
        self.assertAlmostEqual(unlifted.box.bottom - lifted.box.bottom, expected_lift)
        self.assertAlmostEqual(unlifted.box.top - lifted.box.top, expected_lift)
        self.assertAlmostEqual(lifted.box.width / lifted.box.height, 25 / 35)

    def test_space_shortage_shifts_box_inside_without_changing_size(self) -> None:
        face = FaceGeometry(
            bbox_width=400.0,
            eyes_center=Point(100.0, 500.0),
        )

        result = calculate_crop_box(face, 1000, 1200, TargetSize(25, 35))

        self.assertTrue(result.insufficient_space)
        self.assertFalse(result.insufficient_resolution)
        self.assertEqual(result.box.left, 0.0)
        self.assertAlmostEqual(result.box.width, face.bbox_width * K)
        self.assertAlmostEqual(result.box.width / result.box.height, 25 / 35)
        self.assertLessEqual(result.box.right, 1000)
        self.assertLessEqual(result.box.bottom, 1200)

    def test_oversized_box_scales_down_to_image_without_distortion(self) -> None:
        face = FaceGeometry(
            bbox_width=800.0,
            eyes_center=Point(500.0, 500.0),
        )

        result = calculate_crop_box(face, 1000, 1000, TargetSize(25, 35))

        self.assertTrue(result.insufficient_space)
        self.assertFalse(result.insufficient_resolution)
        self.assertGreaterEqual(result.box.left, 0.0)
        self.assertGreaterEqual(result.box.top, 0.0)
        self.assertLessEqual(result.box.right, 1000.0)
        self.assertLessEqual(result.box.bottom, 1000.0)
        self.assertAlmostEqual(result.box.width / result.box.height, 25 / 35)

    def test_resolution_shortage_is_independent_of_space_shortage(self) -> None:
        face = FaceGeometry(
            bbox_width=100.0,
            eyes_center=Point(500.0, 500.0),
        )

        result = calculate_crop_box(face, 1000, 1000, TargetSize(25, 35))

        self.assertFalse(result.insufficient_space)
        self.assertTrue(result.insufficient_resolution)


if __name__ == "__main__":
    unittest.main()
