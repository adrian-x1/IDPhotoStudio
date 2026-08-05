"""MediaPipe Tasks adapter that exposes only reliable crop inputs."""

import math
from pathlib import Path
import sys
from typing import Optional

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions
import numpy as np

from core.crop import FaceGeometry, Point


def _resolve_model_path() -> Path:
    """Return the bundled BlazeFace model path without network fallback."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        base_path = Path(bundle_root)
    else:
        base_path = Path(__file__).resolve().parents[1]
    return base_path / "assets" / "models" / "blaze_face_short_range.tflite"


def detect_face(rgb_image: np.ndarray) -> Optional[FaceGeometry]:
    """Return the largest face's absolute bbox width and eye midpoint."""
    if rgb_image.ndim != 3 or rgb_image.shape[2] != 3:
        return None
    image_height, image_width = rgb_image.shape[:2]
    if image_width <= 0 or image_height <= 0:
        return None

    model_path = _resolve_model_path()
    if not model_path.is_file():
        raise FileNotFoundError(f"missing bundled face detector model: {model_path}")

    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=0.5,
    )
    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=np.ascontiguousarray(rgb_image),
    )
    with FaceDetector.create_from_options(options) as detector:
        result = detector.detect(mp_image)

    candidates = [
        detection
        for detection in result.detections
        if detection.bounding_box is not None
        and detection.bounding_box.width > 0
        and detection.bounding_box.height > 0
        and len(detection.keypoints) >= 2
    ]
    if not candidates:
        return None

    detection = max(
        candidates,
        key=lambda item: item.bounding_box.width * item.bounding_box.height,
    )
    bbox_width = float(detection.bounding_box.width)

    # Tasks bounding boxes are already absolute pixels. Keypoints are normalized
    # coordinates, so both axes must be converted explicitly to absolute pixels.
    right_eye = detection.keypoints[0]
    left_eye = detection.keypoints[1]
    eyes_center = Point(
        x=((right_eye.x + left_eye.x) / 2.0) * image_width,
        y=((right_eye.y + left_eye.y) / 2.0) * image_height,
    )
    values = (bbox_width, eyes_center.x, eyes_center.y)
    if not all(math.isfinite(value) for value in values):
        return None

    return FaceGeometry(bbox_width=bbox_width, eyes_center=eyes_center)
