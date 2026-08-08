from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
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
                patch("core.matting.ort.InferenceSession") as inference_session,
            ):
                with self.assertRaises(FileNotFoundError):
                    matting._get_session()

        inference_session.assert_not_called()

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
            patch(
                "core.matting.ort.InferenceSession", return_value=session
            ) as inference_session,
        ):
            first = matting._get_session()
            second = matting._get_session()

        self.assertIs(first, session)
        self.assertIs(second, session)
        inference_session.assert_called_once()
        self.assertEqual(inference_session.call_args.args, (str(model_path),))
        self.assertEqual(
            inference_session.call_args.kwargs["providers"], ["CPUExecutionProvider"]
        )

    def test_model_path_resolves_inside_the_bundled_asset_directory(self) -> None:
        self.assertEqual(matting._model_path().name, "isnet-general-use.onnx")
        self.assertEqual(matting._model_path().parent, matting._resolve_model_dir())

    def test_extract_foreground_returns_rgba_with_feathered_alpha(self) -> None:
        source = Image.new("RGB", (9, 9), (20, 40, 60))
        mask = Image.new("L", source.size, 0)
        for x in range(5, 9):
            for y in range(9):
                mask.putpixel((x, y), 255)

        with patch("core.matting._predict_alpha", return_value=mask) as predict_alpha:
            foreground = matting.extract_foreground(source)

        self.assertEqual(foreground.mode, "RGBA")
        # Kept pixels retain the source colour and stay nearly opaque, while the
        # background side is cut to transparent black, matching the mask.
        self.assertEqual(foreground.getpixel((8, 4))[:3], (20, 40, 60))
        self.assertGreater(foreground.getpixel((8, 4))[3], 200)
        self.assertEqual(foreground.getpixel((0, 4)), (0, 0, 0, 0))
        # Feathering turns the hard mask edge into a partially opaque seam.
        self.assertGreater(foreground.getpixel((4, 4))[3], 0)
        self.assertLess(foreground.getpixel((4, 4))[3], 255)
        predict_alpha.assert_called_once_with(source)

    def test_predict_alpha_feeds_the_model_a_normalized_square_batch(self) -> None:
        source = Image.new("RGB", (7, 11), (255, 128, 0))

        class FakeSession:
            def __init__(self) -> None:
                self.batch = None

            def get_inputs(self):
                return [SimpleNamespace(name="input")]

            def run(self, _outputs, feed):
                self.batch = feed["input"]
                return [np.zeros((1, 1, 1024, 1024), dtype=np.float32)]

        session = FakeSession()
        with patch("core.matting._get_session", return_value=session):
            mask = matting._predict_alpha(source)

        self.assertEqual(session.batch.shape, (1, 3, 1024, 1024))
        self.assertEqual(session.batch.dtype, np.float32)
        # Channel-first layout normalised around 0.5 keeps values within [-0.5, 0.5].
        self.assertGreaterEqual(session.batch.min(), -0.5)
        self.assertLessEqual(session.batch.max(), 0.5)
        self.assertEqual(mask.mode, "L")
        self.assertEqual(mask.size, source.size)

    def test_composite_background_uses_exact_selected_color(self) -> None:
        foreground = Image.new("RGBA", (2, 1))
        foreground.putdata(((1, 2, 3, 0), (10, 20, 30, 255)))

        result = matting.composite_background(foreground, "蓝")

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.getpixel((0, 0)), (67, 142, 219))
        self.assertEqual(result.getpixel((1, 0)), (10, 20, 30))


if __name__ == "__main__":
    unittest.main()
