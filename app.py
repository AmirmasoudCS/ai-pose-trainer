"""AI Personal Trainer - webcam demo (squats and push-ups) plus recorded-video analysis.

Live mode controls (keyboard or mouse buttons at the top of the window):
  SPACE  start / stop session
  R      reset all counters and the timer
  1 / 2  select Squat / Push-up
  O      open a recorded video and analyze it (uses the selected exercise)
  F      fullscreen on/off
  M      sound on/off
  Q/ESC  quit

Video only (no webcam needed):
  python app.py --video path/to/video.mp4 --exercise squat
"""
import argparse
import math
import sys
import threading
import time

import cv2

from exercises import EXERCISES, RepState
from pose_estimator import PoseEstimator, draw_skeleton
from ui import (BTN_ACTIVE, BTN_IDLE, BTN_START, BTN_STOP, GREEN, GREY, ORANGE, WHITE,
                draw_buttons, fmt_time, panel, text)
from video_analyzer import pick_video_file, run_video_analysis

try:
    import winsound  # Windows only; the beep is simply skipped elsewhere
except ImportError:
    winsound = None

FRAME_WIDTH = 960
WINDOW = "AI Personal Trainer"
COUNTDOWN_SECONDS = 3


class Trainer:
    """Holds the live-session state (selected exercise, counters, timer)."""

    def __init__(self):
        self.names = list(EXERCISES)
        self.counters = {n: EXERCISES[n]() for n in self.names}
        self.seen_counts = {n: 0 for n in self.names}
        self.current = self.names[0]
        self.running = False
        self.run_start = 0.0        # moment counting begins (after the countdown)
        self.elapsed_before = 0.0
        self.muted = False
        self.fullscreen = False
        self.flash_until = 0.0
        self.open_video_requested = False
        self.buttons = []           # rebuilt every frame, used by the mouse callback

    @property
    def counter(self):
        return self.counters[self.current]

    def counting(self, now):
        return self.running and now >= self.run_start

    def countdown_left(self, now):
        return max(0.0, self.run_start - now) if self.running else 0.0

    def elapsed(self, now):
        return self.elapsed_before + (max(0.0, now - self.run_start) if self.running else 0.0)

    def do(self, action):
        now = time.time()
        if action == "toggle":
            if self.running:
                self.elapsed_before += max(0.0, now - self.run_start)
                self.running = False
            else:
                self.counter.restart_motion()
                self.run_start = now + COUNTDOWN_SECONDS
                self.running = True
        elif action == "reset":
            for c in self.counters.values():
                c.reset()
            self.seen_counts = {n: 0 for n in self.names}
            self.elapsed_before = 0.0
            self.run_start = now
        elif action.startswith("select:"):
            name = action.split(":", 1)[1]
            if name in self.counters and name != self.current:
                self.current = name
                self.counter.restart_motion()
        elif action == "video":
            # Handled by the main loop (not inside the mouse callback)
            self.open_video_requested = True
        elif action == "mute":
            self.muted = not self.muted
        elif action == "fullscreen":
            self.fullscreen = not self.fullscreen
            cv2.setWindowProperty(
                WINDOW, cv2.WND_PROP_FULLSCREEN,
                cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL,
            )

    def build_buttons(self):
        """Button layout: (label, (x1, y1, x2, y2), action, color)."""
        buttons, x = [], 315
        for name in self.names:
            color = BTN_ACTIVE if name == self.current else BTN_IDLE
            buttons.append((name, (x, 15, x + 110, 59), f"select:{name}", color))
            x += 120
        buttons.append(("Stop" if self.running else "Start", (x + 5, 15, x + 105, 59),
                        "toggle", BTN_STOP if self.running else BTN_START))
        buttons.append(("Reset", (x + 115, 15, x + 215, 59), "reset", BTN_IDLE))
        buttons.append(("Video", (x + 230, 15, x + 330, 59), "video", BTN_IDLE))
        self.buttons = buttons


def on_mouse(event, x, y, flags, trainer):
    if event == cv2.EVENT_LBUTTONDOWN:
        for _label, (x1, y1, x2, y2), action, _color in trainer.buttons:
            if x1 <= x <= x2 and y1 <= y <= y2:
                trainer.do(action)
                break


def beep():
    if winsound:  # run in a thread so the video never stalls
        threading.Thread(target=winsound.Beep, args=(1000, 90), daemon=True).start()


def open_camera(index):
    # CAP_DSHOW starts much faster on Windows; fall back to the default backend.
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def resolve_exercise(name):
    """Accept 'squat', 'push-up', 'pushup', ... (case-insensitive)."""
    def norm(s):
        return s.lower().replace("-", "").replace("_", "").replace(" ", "")
    for exercise in EXERCISES:
        if norm(exercise) == norm(name):
            return exercise
    raise SystemExit(f"Unknown exercise '{name}'. Choose from: {', '.join(EXERCISES)}")


# ---- drawing ---------------------------------------------------------------
def draw_hud(frame, tr, state, now, fps):
    h, w = frame.shape[:2]

    # Top-left: exercise, reps, timer, status
    panel(frame, 15, 15, 300, 275)
    text(frame, tr.current.upper(), (30, 50), 0.9, GREY)
    text(frame, "REPS", (30, 82), 0.6, GREY, 1)
    text(frame, str(state.count), (30, 158), 2.8, WHITE, 5)
    text(frame, fmt_time(tr.elapsed(now)), (30, 198), 0.8, GREEN if tr.running else GREY)
    text(frame, "REC" if tr.running else "PAUSED", (130, 198), 0.6, GREEN if tr.running else ORANGE, 2)
    if state.angle is not None:
        text(frame, f"Joint angle: {int(state.angle)} deg", (30, 228), 0.5, GREY, 1)
    text(frame, f"Half reps: {state.half_reps}", (30, 255), 0.5, ORANGE if state.half_reps else GREY, 1)

    # Top buttons
    draw_buttons(frame, tr.buttons)

    # Bottom: feedback, controls, fps
    panel(frame, 15, h - 120, w - 15, h - 15)
    text(frame, state.feedback, (35, h - 70), 1.1, GREEN if state.feedback_ok else ORANGE, 3)
    text(frame, "SPACE start/stop  R reset  1/2 exercise  O video  F fullscreen  M sound  Q quit",
         (35, h - 32), 0.5, GREY, 1)
    text(frame, f"FPS {fps:.0f}  Sound {'off' if tr.muted else 'on'}", (w - 200, h - 32), 0.5, GREY, 1)

    # Countdown in the middle of the screen
    left = tr.countdown_left(now)
    if left > 0:
        number = str(math.ceil(left))
        (tw, th), _ = cv2.getTextSize(number, cv2.FONT_HERSHEY_SIMPLEX, 7, 12)
        text(frame, number, ((w - tw) // 2, (h + th) // 2), 7, WHITE, 12)

    # Green border flash when a rep is counted
    if now < tr.flash_until:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), GREEN, 14)


# ---- entry points ----------------------------------------------------------
def run_video_only(path, exercise):
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    try:
        run_video_analysis(path, exercise, WINDOW)
    finally:
        cv2.destroyAllWindows()
    return 0


def main():
    parser = argparse.ArgumentParser(description="AI Personal Trainer")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument("--video", help="analyze a recorded video instead of using the webcam")
    parser.add_argument("--exercise", default="squat", help="exercise for --video: squat or push-up")
    args = parser.parse_args()

    if args.video:
        return run_video_only(args.video, resolve_exercise(args.exercise))

    cap = open_camera(args.camera)
    if not cap.isOpened():
        print("Could not open the webcam. Close other apps using it or try --camera 1.")
        return 1

    estimator = PoseEstimator()
    tr = Trainer()
    t0 = last = time.time()
    fps = 0.0

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, on_mouse, tr)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Lost the camera feed.")
                break

            now = time.time()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-3)
            last = now

            frame = cv2.flip(frame, 1)  # mirror view feels natural
            scale = FRAME_WIDTH / frame.shape[1]
            frame = cv2.resize(frame, (FRAME_WIDTH, int(frame.shape[0] * scale)))

            landmarks = estimator.detect(frame, (now - t0) * 1000)
            draw_skeleton(frame, landmarks)

            counter = tr.counter
            if tr.counting(now):
                state = counter.update(landmarks, now)
                if state.count > tr.seen_counts[tr.current]:
                    tr.flash_until = now + 0.35
                    if not tr.muted:
                        beep()
                tr.seen_counts[tr.current] = state.count
            else:
                msg = "Get ready..." if tr.running else "Press SPACE or click Start"
                state = RepState(counter.count, counter.stage, None, msg, True, counter.half_reps)

            tr.build_buttons()
            draw_hud(frame, tr, state, now, fps)
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break  # window closed with the X button
            if key == ord(" "):
                tr.do("toggle")
            elif key == ord("r"):
                tr.do("reset")
            elif key == ord("f"):
                tr.do("fullscreen")
            elif key == ord("m"):
                tr.do("mute")
            elif key == ord("o"):
                tr.do("video")
            elif ord("1") <= key <= ord("9"):
                i = key - ord("1")
                if i < len(tr.names):
                    tr.do(f"select:{tr.names[i]}")

            if tr.open_video_requested:
                tr.open_video_requested = False
                if tr.running:
                    tr.do("toggle")  # pause the live session
                path = pick_video_file(tr.current)
                if path and not run_video_analysis(path, tr.current, WINDOW):
                    break  # window was closed during the analysis
                last = time.time()
    finally:
        estimator.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())