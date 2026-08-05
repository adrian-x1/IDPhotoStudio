"""Pure geometry for standards-based ID photo cropping.

The four primary constants are geometrically coupled:

* ``CROWN_RATIO`` estimates the real crown from the detector box using
  ``head_top_y = chin_y - (chin_y - bbox_top_y) * CROWN_RATIO``.  The base
  unit is the distance from the chin to the detector box's top edge.
  ``1.7`` is a conservative starting point: a slightly smaller rendered head
  is preferable to cutting off hair, and real samples must calibrate it later.
* ``HEAD_HEIGHT_TARGET`` fixes head height at 66% of the crop height.
* ``EYE_LINE_TARGET`` places the eye line at 45% from the crop top.
* ``HEADROOM_RANGE`` accepts 7% to 12% headroom.

Their dependency is ``headroom = eye_line_ratio - f * head_height_ratio``,
where ``f`` is the eyes' relative position within head height (typically
0.5-0.55).  Changing any one of these constants requires rechecking the other
three; never tune one in isolation.

``FaceGeometry.head_top`` is already extrapolated.  This module neither knows
nor imports the detector implementation.
"""

from dataclasses import dataclass
from typing import Tuple

from core.units import mm_to_px


CROWN_RATIO = 1.7
HEAD_HEIGHT_TARGET = 0.66
EYE_LINE_TARGET = 0.45
HEADROOM_RANGE = (0.07, 0.12)

_HEAD_HEIGHT_RANGE = (0.60, 0.72)
_EYE_LINE_RANGE = (0.43, 0.47)
_AXIS_OFFSET_MAX = 0.01


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class FaceGeometry:
    head_top: Point
    chin: Point
    eyes_center: Point
    face_axis_x: float


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
    headroom_ratio: float
    head_height_ratio: float
    eye_line_ratio: float
    axis_offset_ratio: float
    constraint_violations: Tuple[str, ...]


def calculate_crop_box(
    face: FaceGeometry,
    image_width: float,
    image_height: float,
    target_size: TargetSize,
) -> CropResult:
    """Calculate a crop in head-scale, eye-line, then face-axis order."""
    head_height = face.chin.y - face.head_top.y
    crop_height = head_height / HEAD_HEIGHT_TARGET
    crop_width = crop_height * target_size.width_mm / target_size.height_mm

    top = face.eyes_center.y - EYE_LINE_TARGET * crop_height
    left = face.face_axis_x - crop_width / 2
    ideal_right = left + crop_width
    ideal_bottom = top + crop_height

    insufficient_space = (
        left < 0
        or top < 0
        or ideal_right > image_width
        or ideal_bottom > image_height
    )

    if crop_width > image_width or crop_height > image_height:
        fit_scale = min(image_width / crop_width, image_height / crop_height)
        crop_width *= fit_scale
        crop_height *= fit_scale
        top = face.eyes_center.y - EYE_LINE_TARGET * crop_height
        left = face.face_axis_x - crop_width / 2

    left = min(max(left, 0.0), image_width - crop_width)
    top = min(max(top, 0.0), image_height - crop_height)
    box = CropBox(
        left=left,
        top=top,
        right=left + crop_width,
        bottom=top + crop_height,
    )

    headroom_ratio = (face.head_top.y - box.top) / box.height
    head_height_ratio = head_height / box.height
    eye_line_ratio = (face.eyes_center.y - box.top) / box.height
    crop_axis_x = (box.left + box.right) / 2
    axis_offset_ratio = abs(face.face_axis_x - crop_axis_x) / box.width

    violations = []
    if not HEADROOM_RANGE[0] <= headroom_ratio <= HEADROOM_RANGE[1]:
        violations.append("headroom")
    if not _HEAD_HEIGHT_RANGE[0] <= head_height_ratio <= _HEAD_HEIGHT_RANGE[1]:
        violations.append("head_height")
    if not _EYE_LINE_RANGE[0] <= eye_line_ratio <= _EYE_LINE_RANGE[1]:
        violations.append("eye_line")
    if axis_offset_ratio > _AXIS_OFFSET_MAX:
        violations.append("face_center")

    required_width_px = mm_to_px(target_size.width_mm)
    required_height_px = mm_to_px(target_size.height_mm)
    insufficient_resolution = (
        box.width < required_width_px or box.height < required_height_px
    )

    return CropResult(
        box=box,
        insufficient_space=insufficient_space,
        insufficient_resolution=insufficient_resolution,
        headroom_ratio=headroom_ratio,
        head_height_ratio=head_height_ratio,
        eye_line_ratio=eye_line_ratio,
        axis_offset_ratio=axis_offset_ratio,
        constraint_violations=tuple(violations),
    )
