"""Exercise logic: joint angles, state machines for rep counting, rule-based feedback
and per-repetition statistics.

Educational demo only. The feedback is simple geometry, not a medical or
injury assessment.

MediaPipe landmark indices (left/right):
  shoulder 11/12, elbow 13/14, wrist 15/16, hip 23/24, knee 25/26, ankle 27/28
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
    half_reps: int = 0


def _mean(values):
    return sum(values) / len(values) if values else None


class Exercise:
    """Shared rep-counting machinery.

    A full rep is counted when the main joint angle drops below DOWN_ANGLE and then
    rises back above UP_ANGLE (hysteresis avoids double counts).

    A half rep is a clear attempt (the angle dropped well below START_ANGLE) that
    returned to the top without reaching DOWN_ANGLE. It is not counted as a rep and
    shows "Go lower". Tiny wobbles are ignored.

    Every attempt is stored in `self.attempts` so a summary can be shown afterwards.
    All timestamps come from the `t` argument of update() (seconds), so the same
    code works for the live webcam (wall clock) and for video files (video time).
    """
    name = "Exercise"
    UP_ANGLE = 160
    START_ANGLE = 150
    DOWN_ANGLE = 100
    HALF_REP_MARGIN = 15  # must go this far below START_ANGLE to count as a half rep
    SMOOTHING = 0.4       # 1.0 = no smoothing

    SIDES = ()    # one tuple of landmark indices per body side
    VISIBLE = ()  # positions inside those tuples that must be visible

    def __init__(self):
        self.count = 0
        self.attempts = []
        self._t = time.time()
        self.restart_motion()

    def reset(self):
        """Clear the repetition count, statistics and any movement in progress."""
        self.count = 0
        self.attempts = []
        self.restart_motion()

    def restart_motion(self):
        """Forget the movement in progress but keep the count and statistics."""
        self.stage = "up"
        self._angle = None
        self._descending = False
        self._sticky = None  # (message, ok, expires_at)
        self._rep_start = None
        self._min_angle = None
        self._issue = False

    def update(self, lm, t=None):
        raise NotImplementedError

    @property
    def half_reps(self):
        return sum(1 for a in self.attempts if not a["full"])

    def finish(self, t=None):
        """Call when a video/session ends. A clear movement still in progress is
        stored as a half rep because it was never completed."""
        if t is not None:
            self._t = t
        if (self._descending and self._min_angle is not None
                and self._min_angle < self.START_ANGLE - self.HALF_REP_MARGIN):
            self._record(full=False)
        self.restart_motion()

    def summary(self):
        full = [a for a in self.attempts if a["full"]]
        times = [a["duration"] for a in full]
        depths = [a["min_angle"] for a in full]
        return {
            "exercise": self.name,
            "reps": len(full),
            "half_reps": len(self.attempts) - len(full),
            "form_issue_reps": sum(1 for a in full if a["form_issue"]),
            "good_form_reps": sum(1 for a in full if not a["form_issue"]),
            "avg_rep_time": _mean(times),
            "fastest_rep": min(times) if times else None,
            "slowest_rep": max(times) if times else None,
            "avg_depth": _mean(depths),   # smaller angle = deeper
            "best_depth": min(depths) if depths else None,
            "down_angle": self.DOWN_ANGLE,
            "attempts": list(self.attempts),
        }

    # ---- helpers for subclasses -------------------------------------------
    def _begin_frame(self, t):
        self._t = time.time() if t is None else t

    def _pick_side(self, lm):
        """Use the body side the camera sees best; None if neither is visible."""
        best, best_vis = None, 0.0
        for idx in self.SIDES:
            vis = min(lm[idx[i]][2] for i in self.VISIBLE)
            if vis > best_vis:
                best, best_vis = idx, vis
        return best if best_vis >= MIN_VISIBILITY else None

    def _smooth(self, raw):
        self._angle = raw if self._angle is None else (
            self.SMOOTHING * raw + (1 - self.SMOOTHING) * self._angle
        )
        return self._angle

    def _set_sticky(self, msg, ok, seconds=1.5):
        self._sticky = (msg, ok, self._t + seconds)

    def _sticky_feedback(self):
        if self._sticky and self._t < self._sticky[2]:
            return self._sticky[0], self._sticky[1]
        return None

    def _flag_issue(self):
        """Remember that a form warning appeared during the current rep."""
        if self._descending or self.stage == "down":
            self._issue = True

    def _record(self, full):
        self.attempts.append({
            "start": self._rep_start,
            "end": self._t,
            "duration": self._t - self._rep_start,
            "min_angle": self._min_angle,
            "full": full,
            "form_issue": self._issue,
        })

    def _track_reps(self, angle):
        if self.stage == "up":
            if angle < self.START_ANGLE:
                if not self._descending:
                    self._descending = True
                    self._rep_start = self._t
                    self._min_angle = angle
                    self._issue = False
                self._min_angle = min(self._min_angle, angle)
            if angle < self.DOWN_ANGLE:
                self.stage = "down"
            elif self._descending and angle > self.UP_ANGLE:
                self._descending = False
                if self._min_angle < self.START_ANGLE - self.HALF_REP_MARGIN:
                    self._record(full=False)
                    self._set_sticky("Go lower", False)
        else:  # stage == "down"
            self._min_angle = min(self._min_angle, angle)
            if angle > self.UP_ANGLE:
                self.stage = "up"
                self._descending = False
                self.count += 1
                self._record(full=True)
                self._set_sticky("Good rep!", True, 1.0)

    def _state(self, angle, msg, ok):
        return RepState(self.count, self.stage, angle, msg, ok, self.half_reps)


class SquatCounter(Exercise):
    """Counts squats from the knee angle (hip-knee-ankle), best seen from the side."""
    name = "Squat"
    UP_ANGLE = 160
    START_ANGLE = 150
    DOWN_ANGLE = 100
    MAX_TORSO_LEAN = 70  # degrees from vertical

    SIDES = ((11, 23, 25, 27), (12, 24, 26, 28))  # shoulder, hip, knee, ankle
    VISIBLE = (1, 2, 3)

    def update(self, lm, t=None):
        self._begin_frame(t)
        if lm is None:
            return self._state(None, "No person detected", False)
        side = self._pick_side(lm)
        if side is None:
            return self._state(None, "Step back: show hips, knees and ankles", False)

        shoulder, hip, knee, ankle = (lm[i] for i in side)
        angle = self._smooth(calculate_angle(hip, knee, ankle))
        self._track_reps(angle)

        # Torso lean: angle of the hip->shoulder line from vertical
        dx, dy = shoulder[0] - hip[0], shoulder[1] - hip[1]
        lean = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))
        lean_bad = (self._descending or self.stage == "down") and lean > self.MAX_TORSO_LEAN
        if lean_bad:
            self._flag_issue()

        sticky = self._sticky_feedback()
        if sticky:
            msg, ok = sticky
        elif lean_bad:
            msg, ok = "Keep your chest up", False
        elif self.stage == "down":
            msg, ok = "Good depth - now stand up", True
        elif self._descending:
            msg, ok = "Keep going down", True
        else:
            msg, ok = "Ready - start squatting", True
        return self._state(angle, msg, ok)


class PushUpCounter(Exercise):
    """Counts push-ups from the elbow angle (shoulder-elbow-wrist), side view.

    Only counts while the body is roughly horizontal, so standing up or walking
    around never adds reps. Body alignment is checked with the
    shoulder-hip-ankle (or knee) angle.
    """
    name = "Push-up"
    UP_ANGLE = 155
    START_ANGLE = 140
    DOWN_ANGLE = 95
    MAX_TILT = 40          # max degrees from horizontal (shoulder->hip line)
    MIN_BODY_ANGLE = 150   # below this the body is bent at the hips

    SIDES = ((11, 13, 15, 23, 25, 27), (12, 14, 16, 24, 26, 28))
    VISIBLE = (0, 1, 2, 3)  # shoulder, elbow, wrist, hip

    def update(self, lm, t=None):
        self._begin_frame(t)
        if lm is None:
            return self._state(None, "No person detected", False)
        side = self._pick_side(lm)
        if side is None:
            return self._state(None, "Show your full body from the side", False)

        shoulder, elbow, wrist, hip, knee, ankle = (lm[i] for i in side)

        # Must be in a push-up position (body roughly horizontal)
        tilt = math.degrees(
            math.atan2(abs(hip[1] - shoulder[1]), abs(hip[0] - shoulder[0]) + 1e-6)
        )
        if tilt > self.MAX_TILT:
            self.restart_motion()
            return self._state(None, "Get into push-up position", False)

        angle = self._smooth(calculate_angle(shoulder, elbow, wrist))
        self._track_reps(angle)

        # Body alignment: shoulder-hip-ankle (fall back to knee)
        lower = ankle if ankle[2] >= MIN_VISIBILITY else knee if knee[2] >= MIN_VISIBILITY else None
        aligned = True
        if lower is not None:
            aligned = calculate_angle(shoulder, hip, lower) >= self.MIN_BODY_ANGLE
        if not aligned:
            self._flag_issue()

        sticky = self._sticky_feedback()
        if sticky:
            msg, ok = sticky
        elif not aligned:
            msg, ok = "Keep your body aligned", False
        elif self.stage == "down":
            msg, ok = "Good depth - push up", True
        elif self._descending:
            msg, ok = "Keep going down", True
        else:
            msg, ok = "Good posture", True
        return self._state(angle, msg, ok)


# Exercises available in the UI, in the order of the buttons / number keys.
EXERCISES = {
    "Squat": SquatCounter,
    "Push-up": PushUpCounter,
}