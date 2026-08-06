"""Pure geometry for the measured ID-photo crop.

``H`` controls rendered head size by scaling forehead-to-chin distance.
``EYE_LINE`` controls vertical placement by fixing the eyes within the crop.
``LOWER_EDGE_LIFT_RATIO`` shifts the entire fixed-ratio crop upward to include
less clothing below the shoulders.  All three are adjustable empirical values.
"""

from dataclasses import dataclass

from core.units import mm_to_px


H = 1.8584
EYE_LINE = 0.42
# Fraction of crop height shifted upward to raise the lower edge and reduce
# clothing in frame.  This 5% default is an empirical starting value.
LOWER_EDGE_LIFT_RATIO = 0.05


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class FaceGeometry:
    bbox_width: float
    chin: Point
    forehead: Point
    eyes_center: Point
    roll_degrees: float
    face_height: float


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


def is_insufficient_resolution(
    box: CropBox,
    target_size: TargetSize,
) -> bool:
    """Return whether a crop lacks pixels for its 300 DPI target size."""
    return (
        box.width < mm_to_px(target_size.width_mm)
        or box.height < mm_to_px(target_size.height_mm)
    )


def minimum_face_height_for_300dpi(
    target_size: TargetSize,
    *,
    face_height_scale: float = H,
) -> float:
    """Return the measured face height needed for a 300 DPI automatic crop."""
    required_from_height = mm_to_px(target_size.height_mm) / face_height_scale
    required_from_width = (
        mm_to_px(target_size.width_mm)
        * target_size.height_mm
        / (face_height_scale * target_size.width_mm)
    )
    return max(required_from_height, required_from_width)


def calculate_crop_box(
    face: FaceGeometry,
    image_width: float,
    image_height: float,
    target_size: TargetSize,
    *,
    lower_edge_lift_ratio: float = LOWER_EDGE_LIFT_RATIO,
    face_height_scale: float = H,
) -> CropResult:
    """Calculate a fixed-ratio crop from measured face height and eye position."""
    crop_height = face.face_height * face_height_scale
    crop_width = crop_height * target_size.width_mm / target_size.height_mm

    left = face.eyes_center.x - crop_width / 2
    top = face.eyes_center.y - crop_height * (
        EYE_LINE + lower_edge_lift_ratio
    )
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
        top = face.eyes_center.y - crop_height * (
            EYE_LINE + lower_edge_lift_ratio
        )

    left = min(max(left, 0.0), image_width - crop_width)
    top = min(max(top, 0.0), image_height - crop_height)
    box = CropBox(
        left=left,
        top=top,
        right=left + crop_width,
        bottom=top + crop_height,
    )

    return CropResult(
        box=box,
        insufficient_space=insufficient_space,
        insufficient_resolution=is_insufficient_resolution(box, target_size),
    )
