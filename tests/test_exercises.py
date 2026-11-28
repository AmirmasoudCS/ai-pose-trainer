"""Tests for the counting logic, using simulated body landmarks (no camera needed).

Run:  python -m pytest        (or: python tests/test_exercises.py)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pose_trainer.core.exercises import PushUpCounter, SquatCounter, calculate_angle  # noqa: E402

FPS = 30


def squat_landmarks(knee_angle, lean=0.0):
    """Side view: knee angle in degrees; `lean` shifts the shoulder forward (pixels)."""
    lm = [(0.0, 0.0, 0.0)] * 33
    t = math.radians(knee_angle)
    knee, ankle = (300, 300), (300, 400)
    hip = (300 + 100 * math.sin(t), 300 + 100 * math.cos(t))
    shoulder = (hip[0] + lean, hip[1] - 120)
    for index, point in zip((11, 23, 25, 27), (shoulder, hip, knee, ankle)):
        lm[index] = (point[0], point[1], 0.99)
    return lm


def pushup_landmarks(elbow_angle, hip_y=310, standing=False):
    """Side view of a person in the push-up position (or standing)."""
    lm = [(0.0, 0.0, 0.0)] * 33
    if standing:
        points = {11: (100, 100), 13: (100, 150), 15: (100, 200), 23: (100, 250), 25: (100, 350), 27: (100, 450)}
    else:
        offset = 40 / math.tan(math.radians(elbow_angle / 2)) if elbow_angle < 180 else 0
        points = {11: (100, 300), 13: (100 - offset, 340), 15: (100, 380),
                  23: (260, hip_y), 25: (400, 320), 27: (540, 330)}
    for index, point in points.items():
        lm[index] = (point[0], point[1], 0.99)
    return lm


def ramp(start, end, step=5):
    n = max(1, int(abs(end - start) / step))
    return [start + (end - start) * i / n for i in range(1, n + 1)]


class Clock:
    """Feeds frames to a counter with video-style timestamps."""

    def __init__(self, counter, make_landmarks):
        self.counter, self.make, self.t = counter, make_landmarks, 0.0

    def frame(self, angle, **kwargs):
        state = self.counter.update(self.make(angle, **kwargs), self.t)
        self.t += 1 / FPS
        return state

    def rep(self, top, depth, **kwargs):
        for angle in ramp(top, depth) + ramp(depth, top):
            state = self.frame(angle, **kwargs)
        return state

    def idle(self, top, frames=10):
        for _ in range(frames):
            self.frame(top)


def test_calculate_angle():
    assert round(calculate_angle((0, -1), (0, 0), (0, 1))) == 180
    assert round(calculate_angle((1, 0), (0, 0), (0, 1))) == 90


def test_squat_counts_deep_reps_only():
    c = SquatCounter()
    clock = Clock(c, squat_landmarks)
    for _ in range(3):
        clock.rep(175, 80)
        clock.idle(175)
    assert c.count == 3
    clock.rep(175, 118)  # clear attempt, not deep enough
    assert c.count == 3
    assert c.half_reps == 1


def test_tiny_wobble_is_not_a_half_rep():
    c = SquatCounter()
    clock = Clock(c, squat_landmarks)
    clock.rep(175, 146)  # barely bends the knee
    assert c.count == 0 and c.half_reps == 0


def test_unfinished_movement_is_a_half_rep_on_finish():
    c = SquatCounter()
    clock = Clock(c, squat_landmarks)
    for angle in ramp(175, 110):
        clock.frame(angle)
    c.finish(clock.t)
    assert c.count == 0 and c.half_reps == 1


def test_squat_form_warning_and_statistics():
    c = SquatCounter()
    clock = Clock(c, squat_landmarks)
    clock.rep(175, 80)                 # good rep
    clock.idle(175)
    clock.rep(175, 80, lean=400)       # torso leans far forward (> 70 degrees)
    s = c.summary()
    assert s["reps"] == 2
    assert s["form_issue_reps"] == 1 and s["good_form_reps"] == 1
    assert 0.5 < s["avg_rep_time"] < 3.0     # seconds, from the timestamps (about 1.0 here)
    assert s["best_depth"] < 90


def test_pushups_count_and_ignore_standing():
    c = PushUpCounter()
    clock = Clock(c, pushup_landmarks)
    for _ in range(3):
        clock.rep(175, 70)
        clock.idle(175)
    assert c.count == 3
    before = c.count
    for angle in ramp(175, 50) + ramp(50, 175):  # elbows bending while standing up
        clock.frame(angle, standing=True)
    assert c.count == before


def test_pushup_alignment_warning():
    c = PushUpCounter()
    clock = Clock(c, pushup_landmarks)
    clock.rep(175, 70, hip_y=200)  # hips piked high
    s = c.summary()
    assert s["reps"] == 1 and s["form_issue_reps"] == 1


def test_reset_and_restart_motion():
    c = SquatCounter()
    clock = Clock(c, squat_landmarks)
    clock.rep(175, 80)
    c.restart_motion()
    assert c.count == 1                  # restart keeps the count and the statistics
    c.reset()
    assert c.count == 0 and c.attempts == []


def test_missing_person_and_hidden_legs():
    c = SquatCounter()
    assert c.update(None, 0.0).feedback == "No person detected"
    hidden = [(0.0, 0.0, 0.0)] * 33
    assert "Step back" in c.update(hidden, 0.1).feedback


if __name__ == "__main__":  # run without pytest
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError:
                failed += 1
                print("FAIL", name)
    sys.exit(1 if failed else 0)