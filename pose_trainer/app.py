"""AI Personal Trainer - squats and push-ups with profiles, timed modes and video analysis.

A session = Start ... Stop (or until the timer runs out in a timed mode). When it ends a
results screen is shown and the workout is saved to the selected profile.

Controls (keyboard or mouse buttons):
  SPACE  start / stop the session
  R      discard the current session and clear the counter
  1 / 2  select Squat / Push-up
  T      change mode: Free -> 30 s -> 60 s
  P      profiles (select / create / delete)
  H      progress history of the selected profile
  O      open a recorded video and analyze it (uses the selected exercise)
  F      fullscreen on/off
  M      sound on/off
  Q/ESC  quit

Video only (no webcam needed):
  python main.py --video path/to/video.mp4 --exercise squat [--profile Name]
"""
import argparse
import math
import os
import re
import sys
import threading
import time
from datetime import datetime

import cv2

from pose_trainer.core.exercises import EXERCISES, RepState
from pose_trainer.core.pose_estimator import PoseEstimator, draw_skeleton
from pose_trainer.screens.profile_dialog import manage_profiles
from pose_trainer.paths import RESULTS_DIR
from pose_trainer.storage.profiles import MODES, ProfileStore, mode_label, record_results
from pose_trainer.screens.progress import show_progress
from pose_trainer.screens.results import show_results
from pose_trainer.screens.draw import (BTN_ACTIVE, BTN_ATTN, BTN_IDLE, BTN_START, BTN_STOP, GREEN, GREY, ORANGE, WHITE,
                ascii_text, draw_buttons, fmt_time, panel, text)
from pose_trainer.video_analyzer import pick_video_file, run_video_analysis

try:
    import winsound  # Windows only; the beep is simply skipped elsewhere
except ImportError:
    winsound = None

FRAME_WIDTH = 960
WINDOW = "AI Personal Trainer"
COUNTDOWN_SECONDS = 3
LOCKED_WHILE_RUNNING = ("video", "profile", "progress")


class Trainer:
    """Holds the live-session state (profile, exercise, mode, counters, timer)."""

    def __init__(self, store):
        self.store = store
        self.profile_id = store.last_profile_id
        self.names = list(EXERCISES)
        self.counters = {n: EXERCISES[n]() for n in self.names}
        self.current = self.names[0]
        self.mode = "free"
        self.running = False
        self.run_start = 0.0        # moment counting begins (after the countdown)
        self.frames = 0             # frames processed during the session
        self.pose_frames = 0        # ... of which a body was detected
        self.seen_count = 0
        self.muted = False
        self.fullscreen = False
        self.flash_until = 0.0
        self.pending = None         # slow actions handled by the main loop ("end", "video", ...)
        self.notice = ""
        self.notice_until = 0.0
        self.buttons = []           # rebuilt every frame, used by the mouse callback

    # ---- properties --------------------------------------------------------
    @property
    def counter(self):
        return self.counters[self.current]

    @property
    def profile_name(self):
        profile = self.store.get(self.profile_id) if self.profile_id else None
        return profile["name"] if profile else None

    @property
    def target_seconds(self):
        return MODES[self.mode][1]

    def say(self, message, now, seconds=2.5):
        self.notice, self.notice_until = message, now + seconds

    def active_notice(self, now):
        if now < self.notice_until:
            return self.notice
        if self.profile_name is None and not self.running:
            return "No profile selected - click Profile (P) to create one"
        return ""

    # ---- timing ------------------------------------------------------------
    def counting(self, now):
        return self.running and now >= self.run_start

    def countdown_left(self, now):
        return max(0.0, self.run_start - now) if self.running else 0.0

    def elapsed(self, now):
        return max(0.0, now - self.run_start) if self.running else 0.0

    def time_up(self, now):
        return self.running and self.target_seconds is not None and self.elapsed(now) >= self.target_seconds

    # ---- actions -----------------------------------------------------------
    def start_session(self, now):
        self.counter.reset()
        self.frames = self.pose_frames = self.seen_count = 0
        self.run_start = now + COUNTDOWN_SECONDS
        self.running = True

    def do(self, action):
        now = time.time()
        locked = action.startswith(("select:", "mode:")) or action in LOCKED_WHILE_RUNNING
        if self.running and locked:
            self.say("Stop the session first", now)
            return

        if action == "toggle":
            if self.running:
                self.pending = "end"   # handled by the main loop (shows the results screen)
            else:
                self.start_session(now)
        elif action == "reset":
            if self.running:
                self.running = False
                self.say("Session discarded", now)
            self.counter.reset()
        elif action.startswith("select:"):
            name = action.split(":", 1)[1]
            if name in self.counters and name != self.current:
                self.current = name
                self.counter.reset()
        elif action.startswith("mode:"):
            key = action.split(":", 1)[1]
            if key == "next":
                keys = list(MODES)
                key = keys[(keys.index(self.mode) + 1) % len(keys)]
            if key in MODES:
                self.mode = key
        elif action in LOCKED_WHILE_RUNNING:
            self.pending = action
        elif action == "mute":
            self.muted = not self.muted
        elif action == "fullscreen":
            self.fullscreen = not self.fullscreen
            cv2.setWindowProperty(
                WINDOW, cv2.WND_PROP_FULLSCREEN,
                cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL,
            )

    def end_session(self, now):
        """Stop the running session. Returns a results dict (already saved to the
        profile when one is selected), or None if there is nothing to show."""
        if not self.running:
            return None
        self.running = False
        if now < self.run_start:  # stopped during the countdown
            return None

        target = self.target_seconds
        elapsed = now - self.run_start
        completed = target is not None and elapsed >= target
        duration = target if completed else elapsed

        counter = self.counter
        counter.finish(now)
        summary = counter.summary()
        if not completed and summary["reps"] + summary["half_reps"] == 0:
            return None

        who = self.profile_name or "No profile"
        stamp = datetime.now()
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{who}_{self.current}_{self.mode}_{stamp:%Y%m%d_%H%M%S}")
        results = {
            "video_name": f"{who}  -  {stamp:%Y-%m-%d %H:%M}",
            "image_base": os.path.join(RESULTS_DIR, safe),
            "length_label": "Session length",
            "mode_label": mode_label(self.mode) if self.mode != "free" else "",
            "duration": duration,
            "pose_pct": 100.0 * self.pose_frames / max(self.frames, 1),
            "summary": summary,
        }
        record_results(self.store, self.profile_id, results, self.mode, "live")
        return results

    def build_buttons(self):
        """Button layout: (label, (x1, y1, x2, y2), action, color)."""
        b = []
        x = 315
        for name in self.names:  # row 1: exercises, start/stop, reset
            b.append((name, (x, 15, x + 110, 59), f"select:{name}",
                      BTN_ACTIVE if name == self.current else BTN_IDLE))
            x += 120
        b.append(("Stop" if self.running else "Start", (x + 5, 15, x + 105, 59), "toggle",
                  BTN_STOP if self.running else BTN_START))
        b.append(("Reset", (x + 115, 15, x + 215, 59), "reset", BTN_IDLE))

        x = 315  # row 2: modes, profile, progress, video
        for key, (label, _seconds) in MODES.items():
            b.append((label, (x, 67, x + 80, 105), f"mode:{key}",
                      BTN_ACTIVE if key == self.mode else BTN_IDLE))
            x += 90
        name = self.profile_name
        b.append((ascii_text(name)[:9] if name else "Profile", (x + 10, 67, x + 130, 105), "profile",
                  BTN_IDLE if name else BTN_ATTN))
        b.append(("Progress", (x + 140, 67, x + 260, 105), "progress", BTN_IDLE))
        b.append(("Video", (x + 270, 67, x + 360, 105), "video", BTN_IDLE))
        self.buttons = b


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

    # Top-left: exercise, profile/mode, reps, clock
    panel(frame, 15, 15, 300, 275)
    text(frame, tr.current.upper(), (30, 45), 0.9, GREY)
    who = ascii_text(tr.profile_name)[:14] if tr.profile_name else "No profile"
    text(frame, f"{who}  |  {mode_label(tr.mode)}", (30, 68), 0.5, GREY, 1)
    text(frame, "REPS", (30, 92), 0.55, GREY, 1)
    text(frame, str(state.count), (30, 160), 2.8, WHITE, 5)

    target = tr.target_seconds
    if target is None:
        clock = fmt_time(tr.elapsed(now))
        color = GREEN if tr.running else GREY
        tag = "REC" if tr.running else "READY"
    else:
        remaining = max(0.0, target - tr.elapsed(now)) if tr.running else float(target)
        clock = fmt_time(math.ceil(remaining))
        color = ORANGE if (tr.running and remaining <= 5) else (GREEN if tr.running else GREY)
        tag = "LEFT" if tr.running else "TARGET"
    text(frame, clock, (30, 200), 0.8, color)
    text(frame, tag, (130, 200), 0.6, color, 2)
    if state.angle is not None:
        text(frame, f"Joint angle: {int(state.angle)} deg", (30, 228), 0.5, GREY, 1)
    text(frame, f"Half reps: {state.half_reps}", (30, 255), 0.5, ORANGE if state.half_reps else GREY, 1)

    # Buttons and notice
    draw_buttons(frame, tr.buttons)
    notice = tr.active_notice(now)
    if notice:
        text(frame, notice, (315, 135), 0.6, ORANGE, 2)

    # Bottom: feedback, controls, fps
    panel(frame, 15, h - 125, w - 15, h - 15)
    text(frame, state.feedback, (35, h - 80), 1.1, GREEN if state.feedback_ok else ORANGE, 3)
    text(frame, "SPACE start/stop   R reset   1/2 exercise   T mode   O video",
         (35, h - 52), 0.5, GREY, 1)
    text(frame, "P profile   H progress   F fullscreen   M sound   Q quit",
         (35, h - 28), 0.5, GREY, 1)
    text(frame, f"FPS {fps:.0f}  Sound {'off' if tr.muted else 'on'}", (w - 200, h - 28), 0.5, GREY, 1)

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
def run_video_only(path, exercise, store, profile_name):
    profile_id = store.last_profile_id
    if profile_name:
        profile = store.find_by_name(profile_name)
        if profile is None:
            names = ", ".join(p["name"] for p in store.profiles()) or "(none yet)"
            raise SystemExit(f"No profile named '{profile_name}'. Existing profiles: {names}")
        profile_id = profile["id"]
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    try:
        run_video_analysis(path, exercise, WINDOW, store, profile_id)
    finally:
        cv2.destroyAllWindows()
    return 0


def handle_pending(tr, action):
    """Run a slow action (blocking screens). Returns False if the window was closed."""
    tr.buttons = []  # clicks must not reach the live buttons while another screen is open
    keep_open = True
    now = time.time()
    if action == "end":
        results = tr.end_session(now)
        if results:
            keep_open = show_results(WINDOW, results)
    elif action == "video":
        path = pick_video_file(tr.current)
        if path:
            keep_open = run_video_analysis(path, tr.current, WINDOW, tr.store, tr.profile_id)
    elif action == "profile":
        tr.profile_id = manage_profiles(tr.store, tr.profile_id)
        tr.store.set_last(tr.profile_id)
    elif action == "progress":
        if tr.profile_id is None:
            tr.say("Select or create a profile first (P)", now)
        else:
            keep_open = show_progress(WINDOW, tr.store, tr.profile_id, tr.current, tr.mode)
    return keep_open


def main():
    parser = argparse.ArgumentParser(description="AI Personal Trainer")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument("--video", help="analyze a recorded video instead of using the webcam")
    parser.add_argument("--exercise", default="squat", help="exercise for --video: squat or push-up")
    parser.add_argument("--profile", help="profile name to save a --video analysis to")
    args = parser.parse_args()

    store = ProfileStore()
    if args.video:
        return run_video_only(args.video, resolve_exercise(args.exercise), store, args.profile)

    cap = open_camera(args.camera)
    if not cap.isOpened():
        print("Could not open the webcam. Close other apps using it or try --camera 1.")
        return 1

    estimator = PoseEstimator()
    tr = Trainer(store)
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
            if tr.time_up(now):
                tr.pending = "end"
                state = RepState(counter.count, counter.stage, None, "Time's up!", True, counter.half_reps)
            elif tr.counting(now):
                state = counter.update(landmarks, now)
                tr.frames += 1
                tr.pose_frames += landmarks is not None
                if state.count > tr.seen_count:
                    tr.flash_until = now + 0.35
                    if not tr.muted:
                        beep()
                tr.seen_count = state.count
            else:
                if tr.running:
                    msg = "Get ready..."
                elif tr.target_seconds:
                    msg = f"Press SPACE to start the {mode_label(tr.mode)} test"
                else:
                    msg = "Press SPACE or click Start"
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
            elif key == ord("t"):
                tr.do("mode:next")
            elif key == ord("p"):
                tr.do("profile")
            elif key == ord("h"):
                tr.do("progress")
            elif key == ord("o"):
                tr.do("video")
            elif ord("1") <= key <= ord("9"):
                i = key - ord("1")
                if i < len(tr.names):
                    tr.do(f"select:{tr.names[i]}")

            if tr.pending:
                action, tr.pending = tr.pending, None
                keep_open = handle_pending(tr, action)
                last = time.time()
                if not keep_open:
                    break
    finally:
        estimator.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())