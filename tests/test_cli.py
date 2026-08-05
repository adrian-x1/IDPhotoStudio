from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

import idphoto_cli
from core.crop import FaceGeometry, Point
from core.units import mm_to_px


class CommandLinePipelineTests(unittest.TestCase):
    def test_build_sheet_writes_300dpi_4r_png(self) -> None:
        face = FaceGeometry(
            bbox_width=400.0,
            eyes_center=Point(500.0, 500.0),
        )
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "portrait.jpg"
            output_dir = temp_path / "out"
            Image.new("RGB", (1000, 1200), (80, 100, 120)).save(input_path)

            with (
                patch("idphoto_cli.detect_face", return_value=face) as detect_face,
                patch(
                    "idphoto_cli.replace_background",
                    side_effect=lambda image, background: image.convert("RGB"),
                ) as replace_background,
            ):
                output_path = idphoto_cli.build_sheet(
                    input_path,
                    "一寸",
                    "蓝",
                    output_dir=output_dir,
                )

            self.assertEqual(output_path, output_dir / "portrait_一寸_蓝底.png")
            self.assertTrue(output_path.is_file())
            with Image.open(output_path) as sheet:
                self.assertEqual(sheet.size, (mm_to_px(152), mm_to_px(102)))
                self.assertAlmostEqual(sheet.info["dpi"][0], 300, delta=0.1)
                self.assertAlmostEqual(sheet.info["dpi"][1], 300, delta=0.1)

        detected_image = detect_face.call_args.args[0]
        self.assertEqual(detected_image.shape, (1200, 1000, 3))
        self.assertEqual(replace_background.call_args.args[1], "蓝")


if __name__ == "__main__":
    unittest.main()
