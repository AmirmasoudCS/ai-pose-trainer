"""Exercise logic: joint angles, state machines for rep counting, rule-based feedback.

Educational demo only. The feedback is simple geometry, not a medical or
injury assessment.

Landmark indices (MediaPipe): shoulder 11/12, hip 23/24, knee 25/26, ankle 27/28
(left/right).
"""
import math
import time
from dataclasses import dataclass

MIN_VISIBILITY = 0.5


def calculate_angle(a, b, c):
    """Angle in degrees at point b, formed by points a-b-c (each is (x, y, ...))."""
    ang = math.degrees(
        math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
    )
    ang = abs(ang)
    return 360 - ang if ang > 180 else ang


@dataclass
class RepState:
    count: int = 0
    stage: str = "up"            # "up" or "down"
    angle: float | None = None   # main joint angle shown on screen
    feedback: str = "Get in position"
    feedback_ok: bool = True     # True = positive message, False = correction


class SquatCounter:
    """Counts squats from the knee angle (hip-knee-ankle), best seen from the side.

    Thresholds use hysteresis: standing > 160 deg, bottom < 100 deg.
    A rep is counted when the user reaches the bottom AND returns to standing.
    """
    STAND_ANGLE = 160
    START_ANGLE = 150   # below this we consider the person to be descending
    DEPTH_ANGLE = 100   # below this = deep enough
    MAX_TORSO_LEAN = 70  # degrees from vertical
    SMOOTHING = 0.4      # 1.0 = no smoothing

    LEFT = (11, 23, 25, 27)   # shoulder, hip, knee, ankle
    RIGHT = (12, 24, 26, 28)

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.stage = "up"
        self._angle = None
        self._descending = False
        self._sticky = None  # (message, ok, expires_at)

    def _pick_side(self, lm):
        """Use the body side the camera sees best."""
        best, best_vis = None, 0.0
        for idx in (self.LEFT, self.RIGHT):
            vis = min(lm[i][2] for i in idx[1:])  # hip, knee, ankle
            if vis > best_vis:
                best, best_vis = idx, vis
        return best if best_vis >= MIN_VISIBILITY else None

    def _set_sticky(self, msg, ok, seconds=1.5):
        self._sticky = (msg, ok, time.time() + seconds)

    def update(self, lm):
        """Process one frame of landmarks (or None). Returns a RepState."""
        if lm is None:
            return self._state(None, "No person detected", False)
        side = self._pick_side(lm)
        if side is None:
            return self._state(None, "Step back: show hips, knees and ankles", False)

        shoulder, hip, knee, ankle = (lm[i] for i in side)
        raw = calculate_angle(hip, knee, ankle)
        self._angle = raw if self._angle is None else (
            self.SMOOTHING * raw + (1 - self.SMOOTHING) * self._angle
        )
        angle = self._angle

        if self.stage == "up":
            if angle < self.START_ANGLE:
                self._descending = True
            if angle < self.DEPTH_ANGLE:
                self.stage = "down"
            elif self._descending and angle > self.STAND_ANGLE:
                # Went down a bit but came back up without reaching depth
                self._descending = False
                self._set_sticky("Go lower", False)
        else:  # stage == "down"
            if angle > self.STAND_ANGLE:
                self.stage = "up"
                self._descending = False
                self.count += 1
                self._set_sticky("Good rep!", True, 1.0)

        # Torso lean: angle of hip->shoulder line from vertical
        dx, dy = shoulder[0] - hip[0], shoulder[1] - hip[1]
        lean = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))

        if self._sticky and time.time() < self._sticky[2]:
            msg, ok = self._sticky[0], self._sticky[1]
        elif self._descending and lean > self.MAX_TORSO_LEAN:
            msg, ok = "Keep your chest up", False
        elif self.stage == "down":
            msg, ok = "Good depth - now stand up", True
        elif self._descending:
            msg, ok = "Keep going down", True
        else:
            msg, ok = "Ready - start squatting", True
        return self._state(angle, msg, ok)

    def _state(self, angle, msg, ok):
        return RepState(self.count, self.stage, angle, msg, ok)


# Exercises available in the UI. Push-ups will be added here in Phase 3.
EXERCISES = {
    "Squat": SquatCounter,
}