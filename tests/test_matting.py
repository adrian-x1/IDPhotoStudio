from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from core import matting


class MattingTests(unittest.TestCase):
    def tearDown(self) -> None:
        matting._get_session.cache_clear()

    def test_background_colors_match_plan(self) -> None:
        self.assertEqual(
            matting.BACKGROUND_COLORS,
            {
                "白": (255, 255, 255),
                "蓝": (67, 142, 219),
                "红": (255, 0, 0),
            },
        )

    def test_missing_model_fails_before_creating_session(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing_model = Path(temp_dir) / "isnet-general-use.onnx"
            with (
                patch("core.matting._model_path", return_value=missing_model),
                patch("core.matting.new_session") as new_session,
            ):
                with self.assertRaises(FileNotFoundError):
                    matting._get_session()

        new_session.assert_not_called()

    def test_session_is_created_once_and_reused(self) -> None:
        model_path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "models"
            / "isnet-general-use.onnx"
        )
        session = object()
        with (
            patch("core.matting._model_path", return_value=model_path),
            patch("core.matting.new_session", return_value=session) as new_session,
        ):
            first = matting._get_session()
            second = matting._get_session()

        self.assertIs(first, session)
        self.assertIs(second, session)
        new_session.assert_called_once_with("isnet-general-use")

    def test_extract_foreground_returns_rgba_with_feathered_alpha(self) -> None:
        source = Image.new("RGB", (9, 9), (20, 40, 60))
        sharp = Image.new("RGBA", source.size, (20, 40, 60, 0))
        for x in range(5, 9):
            for y in range(9):
                sharp.putpixel((x, y), (20, 40, 60, 255))

        session = object()
        with (
            patch("core.matting._get_session", return_value=session),
            patch("core.matting.remove", return_value=sharp) as remove,
        ):
            foreground = matting.extract_foreground(source)

        self.assertEqual(foreground.mode, "RGBA")
        self.assertEqual(foreground.getpixel((4, 4))[:3], (20, 40, 60))
        self.assertGreater(foreground.getpixel((4, 4))[3], 0)
        self.assertLess(foreground.getpixel((4, 4))[3], 255)
        remove.assert_called_once_with(source, session=session)

    def test_composite_background_uses_exact_selected_color(self) -> None:
        foreground = Image.new("RGBA", (2, 1))
        foreground.putdata(((1, 2, 3, 0), (10, 20, 30, 255)))

        result = matting.composite_background(foreground, "蓝")

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.getpixel((0, 0)), (67, 142, 219))
        self.assertEqual(result.getpixel((1, 0)), (10, 20, 30))


if __name__ == "__main__":
    unittest.main()
