"""Webcam frame -> body landmarks, using MediaPipe's PoseLandmarker (Tasks API).

Landmarks are returned as a list of 33 tuples: (x_pixel, y_pixel, visibility).
"""
import os
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "pose_landmarker_lite.task")

# Landmark index pairs forming the skeleton (body only, no face details).
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (29, 31), (27, 31), (28, 30), (30, 32), (28, 32),
]
BODY_POINTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]


def ensure_model():
    """Download the pose model once (~5 MB). Afterwards the app works offline."""
    if os.path.exists(MODEL_PATH):
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    print("Downloading pose model (one-time, ~5 MB)...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except Exception as exc:
        if os.path.exists(MODEL_PATH):
            os.remove(MODEL_PATH)
        raise RuntimeError(
            "Could not download the pose model. Download it manually from:\n"
            f"  {MODEL_URL}\n"
            f"and save it as:\n  {MODEL_PATH}"
        ) from exc


class PoseEstimator:
    def __init__(self):
        ensure_model()
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, frame_bgr, timestamp_ms):
        """Return 33 (x, y, visibility) tuples in pixel coordinates, or None."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        timestamp_ms = int(timestamp_ms)
        if timestamp_ms <= self._last_ts:  # MediaPipe needs increasing timestamps
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        if not result.pose_landmarks:
            return None
        h, w = frame_bgr.shape[:2]
        return [(lm.x * w, lm.y * h, lm.visibility) for lm in result.pose_landmarks[0]]

    def close(self):
        self._landmarker.close()


def draw_skeleton(frame, landmarks, line_color=(255, 200, 0), point_color=(0, 255, 120)):
    """Draw the skeleton over the frame (in place)."""
    if landmarks is None:
        return
    for a, b in POSE_CONNECTIONS:
        if landmarks[a][2] > 0.4 and landmarks[b][2] > 0.4:
            pa = (int(landmarks[a][0]), int(landmarks[a][1]))
            pb = (int(landmarks[b][0]), int(landmarks[b][1]))
            cv2.line(frame, pa, pb, line_color, 3, cv2.LINE_AA)
    for i in BODY_POINTS:
        if landmarks[i][2] > 0.4:
            cv2.circle(frame, (int(landmarks[i][0]), int(landmarks[i][1])), 6, point_color, -1, cv2.LINE_AA)