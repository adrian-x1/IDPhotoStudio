import json
from pathlib import Path
import unittest

from core import crop as crop_module
from core.crop import (
    CropBox,
    EYE_LINE,
    H,
    LOWER_EDGE_LIFT_RATIO,
    FaceGeometry,
    Point,
    TargetSize,
    calculate_crop_box,
    minimum_face_height_for_300dpi,
)
from core.units import mm_to_px


class CropGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs_path = Path(__file__).resolve().parents[1] / "specs.json"
        cls.specs = json.loads(specs_path.read_text(encoding="utf-8"))

    @staticmethod
    def face(bbox_width: float, eyes_center: Point) -> FaceGeometry:
        return FaceGeometry(
            bbox_width=bbox_width,
            chin=Point(eyes_center.x, eyes_center.y + bbox_width / 2),
            forehead=Point(eyes_center.x, eyes_center.y - bbox_width / 2),
            eyes_center=eyes_center,
            roll_degrees=0.0,
            face_height=bbox_width,
        )

    def test_all_specs_follow_face_height_geometry(self) -> None:
        face = self.face(1000.0, Point(2000.0, 1500.0))

        for name, spec in self.specs.items():
            with self.subTest(name=name):
                target = TargetSize(spec["width_mm"], spec["height_mm"])
                result = calculate_crop_box(face, 4000, 4000, target)
                box = result.box
                expected_height = face.face_height * H
                expected_width = expected_height * target.width_mm / target.height_mm

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
        face = self.face(1000.0, Point(2000.0, 1500.0))
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
        face = self.face(400.0, Point(100.0, 500.0))

        result = calculate_crop_box(face, 1000, 1200, TargetSize(25, 35))

        self.assertTrue(result.insufficient_space)
        self.assertFalse(result.insufficient_resolution)
        self.assertEqual(result.box.left, 0.0)
        self.assertAlmostEqual(result.box.height, face.face_height * H)
        self.assertAlmostEqual(result.box.width / result.box.height, 25 / 35)
        self.assertLessEqual(result.box.right, 1000)
        self.assertLessEqual(result.box.bottom, 1200)

    def test_oversized_box_scales_down_to_image_without_distortion(self) -> None:
        face = self.face(800.0, Point(500.0, 500.0))

        result = calculate_crop_box(face, 1000, 1000, TargetSize(25, 35))

        self.assertTrue(result.insufficient_space)
        self.assertFalse(result.insufficient_resolution)
        self.assertGreaterEqual(result.box.left, 0.0)
        self.assertGreaterEqual(result.box.top, 0.0)
        self.assertLessEqual(result.box.right, 1000.0)
        self.assertLessEqual(result.box.bottom, 1000.0)
        self.assertAlmostEqual(result.box.width / result.box.height, 25 / 35)

    def test_resolution_shortage_is_independent_of_space_shortage(self) -> None:
        face = self.face(100.0, Point(500.0, 500.0))

        result = calculate_crop_box(face, 1000, 1000, TargetSize(25, 35))

        self.assertFalse(result.insufficient_space)
        self.assertTrue(result.insufficient_resolution)

    def test_manual_crop_reuses_core_resolution_requirement(self) -> None:
        check_resolution = getattr(
            crop_module,
            "is_insufficient_resolution",
            None,
        )
        self.assertIsNotNone(check_resolution)
        if check_resolution is None:
            return

        target = TargetSize(25, 35)
        self.assertFalse(
            check_resolution(CropBox(0, 0, 295, 413), target)
        )
        self.assertTrue(
            check_resolution(CropBox(0, 0, 294, 413), target)
        )
        self.assertTrue(
            check_resolution(CropBox(0, 0, 295, 412), target)
        )

    def test_minimum_face_height_is_derived_from_300dpi_target(self) -> None:
        target = TargetSize(55, 84)

        expected = max(
            mm_to_px(target.height_mm) / H,
            mm_to_px(target.width_mm)
            * target.height_mm
            / (H * target.width_mm),
        )

        self.assertAlmostEqual(
            minimum_face_height_for_300dpi(target),
            expected,
        )


if __name__ == "__main__":
    unittest.main()
