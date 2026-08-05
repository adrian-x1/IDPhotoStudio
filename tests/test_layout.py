import json
from pathlib import Path
import unittest

from PIL import Image, ImageChops

from core.layout import CUT_LINE_COLOR, compose_sheet, solve_layout
from core.units import mm_to_px


EXPECTED_SPECS = {
    "一寸": ((25, 35), (295, 413), (295, 413), 12, (3, 4), False, False),
    "二寸": ((35, 49), (413, 579), (413, 579), 8, (4, 2), False, True),
    "三寸": ((55, 84), (649, 991), (650, 992), 2, (2, 1), False, True),
    "大一寸": ((33, 48), (390, 567), (390, 567), 8, (4, 2), False, True),
    "小一寸": ((22, 32), (260, 378), (260, 378), 18, (6, 3), False, True),
    "大二寸": ((35, 53), (413, 626), (413, 626), 4, (4, 1), False, True),
    "小二寸": ((35, 45), (413, 531), (413, 531), 8, (4, 2), False, True),
    "简历照": ((25, 35), (295, 413), (295, 413), 12, (3, 4), False, False),
    "普通话水平测试": ((33, 48), (390, 567), (390, 567), 8, (4, 2), False, True),
    "英语四六级": ((12, 16), (144, 192), (142, 189), 56, (7, 8), False, False),
}


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        specs_path = Path(__file__).resolve().parents[1] / "specs.json"
        cls.specs = json.loads(specs_path.read_text(encoding="utf-8"))

    def test_specs_match_required_options_and_digital_pixels(self) -> None:
        self.assertEqual(set(self.specs), set(EXPECTED_SPECS))

        for name, (size_mm, digital_px, *_) in EXPECTED_SPECS.items():
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
        for name, (
            size_mm,
            _,
            print_px,
            count,
            grid,
            photo_rotated,
            paper_rotated,
        ) in EXPECTED_SPECS.items():
            with self.subTest(name=name):
                width_mm, height_mm = size_mm
                result = solve_layout(width_mm, height_mm)

                self.assertEqual(
                    (mm_to_px(width_mm), mm_to_px(height_mm)),
                    print_px,
                )
                self.assertEqual(result.count, count)
                self.assertEqual((result.columns, result.rows), grid)
                self.assertEqual(result.photo_rotated, photo_rotated)
                self.assertEqual(result.paper_rotated, paper_rotated)
                self.assertEqual(
                    (result.paper_width_mm, result.paper_height_mm),
                    (152, 102) if paper_rotated else (102, 152),
                )

    def test_compose_sheet_centers_entire_grid_on_4r_canvas(self) -> None:
        photo_width_mm = 25
        photo_height_mm = 35
        gap_mm = 1.0
        layout = solve_layout(photo_width_mm, photo_height_mm, gap=gap_mm)
        photo = Image.new("RGB", (200, 280), (180, 20, 30))

        sheet = compose_sheet(
            photo,
            photo_width_mm,
            photo_height_mm,
            layout,
            gap=gap_mm,
            draw_cut_lines=False,
        )

        self.assertEqual(
            sheet.size,
            (
                mm_to_px(layout.paper_width_mm),
                mm_to_px(layout.paper_height_mm),
            ),
        )

        placed_width_mm = photo_height_mm if layout.photo_rotated else photo_width_mm
        placed_height_mm = photo_width_mm if layout.photo_rotated else photo_height_mm
        grid_width_mm = layout.columns * placed_width_mm + (layout.columns - 1) * gap_mm
        grid_height_mm = layout.rows * placed_height_mm + (layout.rows - 1) * gap_mm
        start_x_mm = (layout.paper_width_mm - grid_width_mm) / 2
        start_y_mm = (layout.paper_height_mm - grid_height_mm) / 2
        expected_left = mm_to_px(start_x_mm)
        expected_top = mm_to_px(start_y_mm)
        expected_right = (
            mm_to_px(start_x_mm + (layout.columns - 1) * (placed_width_mm + gap_mm))
            + mm_to_px(placed_width_mm)
        )
        expected_bottom = (
            mm_to_px(start_y_mm + (layout.rows - 1) * (placed_height_mm + gap_mm))
            + mm_to_px(placed_height_mm)
        )

        white = Image.new("RGB", sheet.size, "white")
        self.assertEqual(
            ImageChops.difference(sheet, white).getbbox(),
            (expected_left, expected_top, expected_right, expected_bottom),
        )
        self.assertLessEqual(abs(expected_left - (sheet.width - expected_right)), 1)
        self.assertLessEqual(abs(expected_top - (sheet.height - expected_bottom)), 1)

    def test_cut_lines_are_optional_and_use_03mm_light_gray(self) -> None:
        layout = solve_layout(25, 35)
        photo = Image.new("RGB", (200, 280), (180, 20, 30))
        without_lines = compose_sheet(
            photo,
            25,
            35,
            layout,
            draw_cut_lines=False,
        )
        with_lines = compose_sheet(
            photo,
            25,
            35,
            layout,
            draw_cut_lines=True,
        )

        placed_width_mm = 35 if layout.photo_rotated else 25
        placed_height_mm = 25 if layout.photo_rotated else 35
        grid_width_mm = layout.columns * placed_width_mm + layout.columns - 1
        grid_height_mm = layout.rows * placed_height_mm + layout.rows - 1
        x = mm_to_px((layout.paper_width_mm - grid_width_mm) / 2)
        y = mm_to_px((layout.paper_height_mm - grid_height_mm) / 2)

        self.assertEqual(without_lines.getpixel((x, y)), (180, 20, 30))
        self.assertEqual(with_lines.getpixel((x, y)), CUT_LINE_COLOR)
        self.assertEqual(with_lines.getpixel((x + mm_to_px(0.3) + 1, y + mm_to_px(0.3) + 1)), (180, 20, 30))


if __name__ == "__main__":
    unittest.main()
