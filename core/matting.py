"""Offline foreground extraction and fixed-color background replacement."""

from functools import lru_cache
import os
from pathlib import Path
import sys

from PIL import Image, ImageFilter


def _resolve_model_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        base_path = Path(bundle_root)
    else:
        base_path = Path(__file__).resolve().parents[1]
    return base_path / "assets" / "models"


# rembg reads these variables when constructing a session.  The model is always
# bundled with the app; disabling checksum fallback prevents replacement of the
# local file and the explicit existence check below prevents a download attempt.
os.environ["U2NET_HOME"] = str(_resolve_model_dir())
os.environ["MODEL_CHECKSUM_DISABLED"] = "1"

from rembg import new_session, remove  # noqa: E402


BACKGROUND_COLORS = {
    "白": (255, 255, 255),
    "蓝": (67, 142, 219),
    "红": (255, 0, 0),
}
ALPHA_FEATHER_RADIUS = 1.5


def _model_path() -> Path:
    return Path(os.environ["U2NET_HOME"]) / "isnet-general-use.onnx"


@lru_cache(maxsize=1)
def _get_session():
    model_path = _model_path()
    if not model_path.is_file():
        raise FileNotFoundError(f"missing bundled matting model: {model_path}")
    return new_session("isnet-general-use")


def feather_alpha(foreground: Image.Image) -> Image.Image:
    """Apply a light 1.5px Gaussian blur to an RGBA image's alpha only."""
    rgba = foreground.convert("RGBA")
    alpha = rgba.getchannel("A").filter(
        ImageFilter.GaussianBlur(radius=ALPHA_FEATHER_RADIUS)
    )
    rgba.putalpha(alpha)
    return rgba


def extract_foreground(image: Image.Image) -> Image.Image:
    """Run offline rembg inference and return a lightly feathered RGBA image."""
    source = image if image.mode == "RGB" else image.convert("RGB")
    foreground = remove(source, session=_get_session())
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
