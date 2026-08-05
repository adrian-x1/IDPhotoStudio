"""MediaPipe Face Detection adapter for the pure crop geometry API."""

from typing import Optional

import mediapipe as mp
import numpy as np

from core.crop import CROWN_RATIO, FaceGeometry, Point


def detect_face(
    rgb_image: np.ndarray,
    model_selection: int = 0,
    min_detection_confidence: float = 0.5,
) -> Optional[FaceGeometry]:
    """Detect the most prominent face and return absolute pixel geometry."""
    image_height, image_width = rgb_image.shape[:2]
    if image_width <= 0 or image_height <= 0:
        return None

    face_detection = mp.solutions.face_detection
    with face_detection.FaceDetection(
        model_selection=model_selection,
        min_detection_confidence=min_detection_confidence,
    ) as detector:
        results = detector.process(rgb_image)

    if not results.detections:
        return None

    detection = max(
        results.detections,
        key=lambda item: (
            item.location_data.relative_bounding_box.width
            * item.location_data.relative_bounding_box.height
        ),
    )
    bounding_box = detection.location_data.relative_bounding_box
    if bounding_box.width <= 0 or bounding_box.height <= 0:
        return None

    left_eye = face_detection.get_key_point(
        detection,
        face_detection.FaceKeyPoint.LEFT_EYE,
    )
    right_eye = face_detection.get_key_point(
        detection,
        face_detection.FaceKeyPoint.RIGHT_EYE,
    )
    if left_eye is None or right_eye is None:
        return None

    eyes_center = Point(
        x=(left_eye.x + right_eye.x) * image_width / 2,
        y=(left_eye.y + right_eye.y) * image_height / 2,
    )
    face_axis_x = eyes_center.x

    bbox_top_y = bounding_box.ymin * image_height
    chin_y = (bounding_box.ymin + bounding_box.height) * image_height
    head_top_y = chin_y - (chin_y - bbox_top_y) * CROWN_RATIO

    return FaceGeometry(
        head_top=Point(face_axis_x, head_top_y),
        chin=Point(face_axis_x, chin_y),
        eyes_center=eyes_center,
        face_axis_x=face_axis_x,
    )
