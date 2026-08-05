"""Physical unit conversion for the 300 DPI output pipeline."""

DPI = 300
MM_PER_INCH = 25.4


def mm_to_px(mm: float) -> int:
    """Convert millimetres to pixels at the project-wide output resolution."""
    return round(mm / MM_PER_INCH * DPI)


def px_to_mm(px: float) -> float:
    """Convert pixels to millimetres at the project-wide output resolution."""
    return px / DPI * MM_PER_INCH
