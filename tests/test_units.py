import unittest

from core.units import mm_to_px, px_to_mm


class UnitConversionTests(unittest.TestCase):
    def test_mm_to_px_uses_300_dpi(self) -> None:
        one_inch_mm = 254 / 10
        self.assertEqual(mm_to_px(one_inch_mm), 300)
        self.assertEqual(mm_to_px(102), 1205)
        self.assertEqual(mm_to_px(152), 1795)

    def test_px_to_mm_uses_300_dpi(self) -> None:
        one_inch_mm = 254 / 10
        self.assertAlmostEqual(px_to_mm(300), one_inch_mm)


if __name__ == "__main__":
    unittest.main()
