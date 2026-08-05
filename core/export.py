"""Export completed sheet images without UI or layout dependencies."""

from __future__ import annotations

from os import PathLike

from PIL import Image


OUTPUT_DPI = 300


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
