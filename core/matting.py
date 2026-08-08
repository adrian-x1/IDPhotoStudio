"""Offline foreground extraction and fixed-color background replacement."""

from functools import lru_cache
from pathlib import Path
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter


def _resolve_model_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        base_path = Path(bundle_root)
    else:
        base_path = Path(__file__).resolve().parents[1]
    return base_path / "assets" / "models"


BACKGROUND_COLORS = {
    "白": (255, 255, 255),
    "蓝": (67, 142, 219),
    "红": (255, 0, 0),
}
ALPHA_FEATHER_RADIUS = 1.5

# The isnet-general-use network expects a fixed 1024x1024 input normalised to
# a mean of 0.5 and a standard deviation of 1.0.  These values reproduce the
# preprocessing rembg applied, which the pinned model was trained against.
_MODEL_INPUT_SIZE = (1024, 1024)
_NORMALIZE_MEAN = 0.5
_NORMALIZE_STD = 1.0


def _model_path() -> Path:
    return _resolve_model_dir() / "isnet-general-use.onnx"


@lru_cache(maxsize=1)
def _get_session() -> ort.InferenceSession:
    model_path = _model_path()
    if not model_path.is_file():
        raise FileNotFoundError(f"missing bundled matting model: {model_path}")
    return ort.InferenceSession(
        str(model_path),
        sess_options=ort.SessionOptions(),
        providers=["CPUExecutionProvider"],
    )


def _predict_alpha(image: Image.Image) -> Image.Image:
    """Infer a soft foreground mask sized to match ``image``."""
    resized = image.resize(_MODEL_INPUT_SIZE, Image.Resampling.LANCZOS)
    samples = np.array(resized)
    samples = samples / max(np.max(samples), 1e-6)

    normalized = np.zeros(
        (samples.shape[0], samples.shape[1], 3), dtype=samples.dtype
    )
    for channel in range(3):
        normalized[:, :, channel] = (
            samples[:, :, channel] - _NORMALIZE_MEAN
        ) / _NORMALIZE_STD
    batch = np.expand_dims(normalized.transpose((2, 0, 1)), 0).astype(np.float32)

    session = _get_session()
    prediction = session.run(None, {session.get_inputs()[0].name: batch})[0]
    prediction = prediction[:, 0, :, :]

    # Rescale the raw logits into the full 0-1 range before quantising to 8 bit.
    # A uniform prediction has no range to stretch, so guard the division to
    # avoid the NaN mask that would otherwise reach the caller.
    lowest = prediction.min()
    span = prediction.max() - lowest
    prediction = (prediction - lowest) / span if span > 0 else np.zeros_like(prediction)

    mask = Image.fromarray(
        (np.squeeze(prediction) * 255).astype("uint8"), mode="L"
    )
    return mask.resize(image.size, Image.Resampling.LANCZOS)


def feather_alpha(foreground: Image.Image) -> Image.Image:
    """Apply a light 1.5px Gaussian blur to an RGBA image's alpha only."""
    rgba = foreground.convert("RGBA")
    alpha = rgba.getchannel("A").filter(
        ImageFilter.GaussianBlur(radius=ALPHA_FEATHER_RADIUS)
    )
    rgba.putalpha(alpha)
    return rgba


def extract_foreground(image: Image.Image) -> Image.Image:
    """Run offline ONNX inference and return a lightly feathered RGBA image."""
    source = image if image.mode == "RGB" else image.convert("RGB")
    mask = _predict_alpha(source)
    foreground = Image.composite(source, Image.new("RGBA", source.size, 0), mask)
    return feather_alpha(foreground)


def composite_background(foreground: Image.Image, background: str) -> Image.Image:
    """Composite an RGBA foreground over one of the three plan colors."""
    try:
        color = BACKGROUND_COLORS[background]
    except KeyError as error:
        choices = ", ".join(BACKGROUND_COLORS)
        raise ValueError(f"unknown background {background!r}; choose {choices}") from error

    rgba = foreground.convert("RGBA")
    background_image = Image.new("RGBA", rgba.size, color + (255,))
    return Image.alpha_composite(background_image, rgba).convert("RGB")


def replace_background(image: Image.Image, background: str) -> Image.Image:
    """Extract a foreground and composite it over the selected fixed color."""
    return composite_background(extract_foreground(image), background)
