import json
from pathlib import Path
import unittest

from core.layout import solve_layout
from core.units import mm_to_px


EXPECTED_SPECS = {
    "一寸": ((25, 35), (295, 413), (295, 413), 12, (4, 3)),
    "二寸": ((35, 49), (413, 579), (413, 579), 8, (4, 2)),
    "三寸": ((55, 84), (649, 991), (650, 992), 2, (2, 1)),
    "大一寸": ((33, 48), (390, 567), (390, 567), 8, (4, 2)),
    "小一寸": ((22, 32), (260, 378), (260, 378), 18, (6, 3)),
    "大二寸": ((35, 53), (413, 626), (413, 626), 4, (4, 1)),
    "小二寸": ((35, 45), (413, 531), (413, 531), 8, (4, 2)),
    "简历照": ((25, 35), (295, 413), (295, 413), 12, (4, 3)),
    "普通话水平测试": ((33, 48), (390, 567), (390, 567), 8, (4, 2)),
    "英语四六级": ((12, 16), (144, 192), (142, 189), 56, (8, 7)),
}


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs_path = Path(__file__).resolve().parents[1] / "specs.json"
        cls.specs = json.loads(specs_path.read_text(encoding="utf-8"))

    def test_specs_match_required_options_and_digital_pixels(self) -> None:
        self.assertEqual(set(self.specs), set(EXPECTED_SPECS))

        for name, (size_mm, digital_px, _, _, _) in EXPECTED_SPECS.items():
            with self.subTest(name=name):
                spec = self.specs[name]
                self.assertEqual(
                    (spec["width_mm"], spec["height_mm"]),
                    size_mm,
                )
                self.assertEqual(
                    (spec["digital_width_px"], spec["digital_height_px"]),
                    digital_px,
                )

    def test_layout_solver_matches_plan_acceptance_table(self) -> None:
        for name, (size_mm, _, print_px, count, grid) in EXPECTED_SPECS.items():
            with self.subTest(name=name):
                width_mm, height_mm = size_mm
                result = solve_layout(width_mm, height_mm)

                self.assertEqual(
                    (mm_to_px(width_mm), mm_to_px(height_mm)),
                    print_px,
                )
                self.assertEqual(result.count, count)
                self.assertEqual((result.columns, result.rows), grid)
                self.assertTrue(result.paper_rotated)
                self.assertEqual(
                    (result.paper_width_mm, result.paper_height_mm),
                    (152, 102),
                )


if __name__ == "__main__":
    unittest.main()
