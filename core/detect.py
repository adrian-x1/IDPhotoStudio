"""MediaPipe FaceLandmarker adapter for crop geometry."""

from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Optional, Sequence

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions
import numpy as np

from core.crop import FaceGeometry, Point


@dataclass(frozen=True)
class FaceDetectionResult:
    geometry: FaceGeometry
    face_count: int


@dataclass(frozen=True)
class _FaceCandidate:
    geometry: FaceGeometry
    envelope_area: float


def _resolve_model_path() -> Path:
    """Return the bundled FaceLandmarker model path without network fallback."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        base_path = Path(bundle_root)
    else:
        base_path = Path(__file__).resolve().parents[1]
    return base_path / "assets" / "models" / "face_landmarker.task"


def _absolute_point(landmark, image_width: int, image_height: int) -> Point:
    return Point(
        x=float(landmark.x) * image_width,
        y=float(landmark.y) * image_height,
    )


def _centroid(
    landmarks: Sequence,
    indices: range,
    image_width: int,
    image_height: int,
) -> Point:
    points = [
        _absolute_point(landmarks[index], image_width, image_height)
        for index in indices
    ]
    return Point(
        x=sum(point.x for point in points) / len(points),
        y=sum(point.y for point in points) / len(points),
    )


def _normalize_roll(degrees: float) -> float:
    return (degrees + 90.0) % 180.0 - 90.0


def _candidate_from_landmarks(
    landmarks: Sequence,
    image_width: int,
    image_height: int,
) -> Optional[_FaceCandidate]:
    """Convert one 478-point face mesh into absolute crop geometry."""
    if len(landmarks) < 478:
        return None
    required_indices = (10, 33, 152, 263, *range(468, 478))
    required_values = (
        coordinate
        for index in required_indices
        for coordinate in (landmarks[index].x, landmarks[index].y)
    )
    if not all(math.isfinite(float(value)) for value in required_values):
        return None

    absolute_points = [
        _absolute_point(landmark, image_width, image_height)
        for landmark in landmarks
    ]
    if not all(
        math.isfinite(coordinate)
        for point in absolute_points
        for coordinate in (point.x, point.y)
    ):
        return None
    min_x = min(point.x for point in absolute_points)
    max_x = max(point.x for point in absolute_points)
    min_y = min(point.y for point in absolute_points)
    max_y = max(point.y for point in absolute_points)
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    if bbox_width <= 0.0 or bbox_height <= 0.0:
        return None

    forehead = absolute_points[10]
    chin = absolute_points[152]
    face_height = math.hypot(
        chin.x - forehead.x,
        chin.y - forehead.y,
    )
    right_iris = _centroid(
        landmarks,
        range(468, 473),
        image_width,
        image_height,
    )
    left_iris = _centroid(
        landmarks,
        range(473, 478),
        image_width,
        image_height,
    )
    eyes_center = Point(
        x=(right_iris.x + left_iris.x) / 2.0,
        y=(right_iris.y + left_iris.y) / 2.0,
    )
    outer_right = absolute_points[33]
    outer_left = absolute_points[263]
    roll_degrees = _normalize_roll(
        math.degrees(
            math.atan2(
                outer_left.y - outer_right.y,
                outer_left.x - outer_right.x,
            )
        )
    )
    values = (
        bbox_width,
        chin.x,
        chin.y,
        forehead.x,
        forehead.y,
        eyes_center.x,
        eyes_center.y,
        roll_degrees,
        face_height,
    )
    if face_height <= 0.0 or not all(math.isfinite(value) for value in values):
        return None

    return _FaceCandidate(
        geometry=FaceGeometry(
            bbox_width=bbox_width,
            chin=chin,
            forehead=forehead,
            eyes_center=eyes_center,
            roll_degrees=roll_degrees,
            face_height=face_height,
        ),
        envelope_area=bbox_width * bbox_height,
    )


def _select_largest_face(
    face_landmarks: Sequence[Sequence],
    image_width: int,
    image_height: int,
) -> Optional[FaceDetectionResult]:
    candidates = [
        candidate
        for landmarks in face_landmarks
        if (
            candidate := _candidate_from_landmarks(
                landmarks,
                image_width,
                image_height,
            )
        )
        is not None
    ]
    if not candidates:
        return None
    largest = max(candidates, key=lambda candidate: candidate.envelope_area)
    return FaceDetectionResult(
        geometry=largest.geometry,
        face_count=len(face_landmarks),
    )


def detect_face(rgb_image: np.ndarray) -> Optional[FaceDetectionResult]:
    """Return the largest valid face and the number of detected faces."""
    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3:
        return None
    image_height, image_width = rgb_image.shape[:2]
    if image_width <= 0 or image_height <= 0:
        return None

    model_path = _resolve_model_path()
    if not model_path.is_file():
        raise FileNotFoundError(f"missing bundled face landmarker model: {model_path}")

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        num_faces=5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=np.ascontiguousarray(rgb_image),
    )
    with FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp_image)

    return _select_largest_face(
        result.face_landmarks,
        image_width,
        image_height,
    )
