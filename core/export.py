"""Export completed sheet images without UI or layout dependencies."""

from __future__ import annotations

from os import PathLike

from PIL import Image

from core.units import DPI, mm_to_px


OUTPUT_DPI = DPI


def export_jpeg(
    image: Image.Image,
    path: str | PathLike[str],
    *,
    quality: int = 95,
) -> None:
    """Save an image as an opaque 4:4:4 JPEG at the output resolution."""
    image.convert("RGB").save(
        path,
        format="JPEG",
        quality=quality,
        subsampling=0,
        dpi=(OUTPUT_DPI, OUTPUT_DPI),
    )


def render_photo(
    photo: Image.Image,
    width_mm: float,
    height_mm: float,
    *,
    resample=Image.Resampling.LANCZOS,
) -> Image.Image:
    """Resize one completed photo to its exact physical size at 300 DPI."""
    return photo.resize(
        (mm_to_px(width_mm), mm_to_px(height_mm)),
        resample=resample,
    )


def export_png(
    sheet_image: Image.Image,
    path: str | PathLike[str],
) -> None:
    """Save a completed sheet as a 300 DPI PNG."""
    sheet_image.save(
        path,
        format="PNG",
        dpi=(OUTPUT_DPI, OUTPUT_DPI),
    )


def export_pdf(
    sheet_image: Image.Image,
    path: str | PathLike[str],
) -> None:
    """Save a completed sheet as a PDF whose page follows its pixel size."""
    sheet_image.convert("RGB").save(
        path,
        format="PDF",
        resolution=OUTPUT_DPI,
    )
