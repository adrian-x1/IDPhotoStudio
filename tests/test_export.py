import re
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from core.export import export_pdf, export_png
from core.layout import compose_sheet, solve_layout


MEDIA_BOX_PATTERN = re.compile(
    rb"/MediaBox\s*\[\s*([-+\d.]+)\s+([-+\d.]+)\s+"
    rb"([-+\d.]+)\s+([-+\d.]+)\s*\]"
)


def _media_box(path: Path) -> tuple[float, float, float, float]:
    match = MEDIA_BOX_PATTERN.search(path.read_bytes())
    if match is None:
        raise AssertionError("PDF does not contain a MediaBox")
    return tuple(float(value) for value in match.groups())


def _physical_pixel_density(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        if chunk_type == b"pHYs":
            return struct.unpack(">IIB", chunk_data)
        offset += 12 + length
    raise AssertionError("PNG does not contain a pHYs chunk")


class ExportTests(unittest.TestCase):
    def test_export_png_preserves_pixels_and_writes_300_dpi_phys(self) -> None:
        image = Image.new("RGB", (1205, 1795), "white")

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "一寸_4R.png"
            export_png(image, path)

            with Image.open(path) as exported:
                self.assertEqual(exported.size, image.size)
                self.assertAlmostEqual(exported.info["dpi"][0], 300, delta=0.01)
                self.assertAlmostEqual(exported.info["dpi"][1], 300, delta=0.01)
            self.assertEqual(_physical_pixel_density(path), (11811, 11811, 1))

    def test_export_pdf_uses_image_pixels_as_300_dpi_page_size(self) -> None:
        image = Image.new("RGB", (1205, 1795), "white")

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "一寸_4R.pdf"
            export_pdf(image, path)

            media_box = _media_box(path)

        expected = (0.0, 0.0, 289.2, 430.8)
        for actual, target in zip(media_box, expected, strict=True):
            self.assertAlmostEqual(actual, target, delta=1.0)

    def test_three_inch_landscape_pdf_is_wider_than_tall(self) -> None:
        layout = solve_layout(55, 84)
        self.assertGreater(layout.paper_width_mm, layout.paper_height_mm)
        photo = Image.new("RGB", (650, 992), "white")
        sheet = compose_sheet(photo, 55, 84, layout)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "三寸_4R.pdf"
            export_pdf(sheet, path)
            _, _, width, height = _media_box(path)

        self.assertGreater(width, height)


if __name__ == "__main__":
    unittest.main()
