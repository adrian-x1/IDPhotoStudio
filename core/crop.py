"""Pure geometry for the measured two-parameter ID-photo crop.

``K`` controls rendered head size by scaling the detector's face-box width.
``EYE_LINE`` controls vertical placement by fixing the eyes within the crop.
Both are independently adjustable empirical values measured from real samples.
"""

from dataclasses import dataclass

from core.units import mm_to_px


K = 1.55
EYE_LINE = 0.42


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class FaceGeometry:
    bbox_width: float
    eyes_center: Point


@dataclass(frozen=True)
class TargetSize:
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class CropBox:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class CropResult:
    box: CropBox
    insufficient_space: bool
    insufficient_resolution: bool


def calculate_crop_box(
    face: FaceGeometry,
    image_width: float,
    image_height: float,
    target_size: TargetSize,
) -> CropResult:
    """Calculate a fixed-ratio crop from face-box width and eye position."""
    crop_width = face.bbox_width * K
    crop_height = crop_width * target_size.height_mm / target_size.width_mm

    left = face.eyes_center.x - crop_width / 2
    top = face.eyes_center.y - crop_height * EYE_LINE
    insufficient_space = (
        left < 0
        or top < 0
        or left + crop_width > image_width
        or top + crop_height > image_height
    )

    if crop_width > image_width or crop_height > image_height:
        fit_scale = min(image_width / crop_width, image_height / crop_height)
        crop_width *= fit_scale
        crop_height *= fit_scale
        left = face.eyes_center.x - crop_width / 2
        top = face.eyes_center.y - crop_height * EYE_LINE

    left = min(max(left, 0.0), image_width - crop_width)
    top = min(max(top, 0.0), image_height - crop_height)
    box = CropBox(
        left=left,
        top=top,
        right=left + crop_width,
        bottom=top + crop_height,
    )

    insufficient_resolution = (
        box.width < mm_to_px(target_size.width_mm)
        or box.height < mm_to_px(target_size.height_mm)
    )
    return CropResult(
        box=box,
        insufficient_space=insufficient_space,
        insufficient_resolution=insufficient_resolution,
    )
