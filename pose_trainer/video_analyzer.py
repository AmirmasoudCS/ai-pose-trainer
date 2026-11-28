"""Analyze a recorded video: play it, track the body, count reps, then show a results screen.

Keys while the video plays:
  SPACE  pause / resume
  T      fast-forward on/off (process as fast as possible)
  Q/ESC  stop early and show the results
"""
import os
import time

import cv2
import numpy as np

from pose_trainer.core.exercises import EXERCISES
from pose_trainer.core.pose_estimator import PoseEstimator, draw_skeleton
from pose_trainer.storage.profiles import record_results
from pose_trainer.screens.results import show_results
from pose_trainer.screens.draw import GREEN, GREY, ORANGE, WHITE, fmt_time, panel, text

CANVAS_W, CANVAS_H = 960, 540
VIDEO_TYPES = [
    ("Video files", "*.mp4 *.mov *.avi *.mkv *.m4v *.wmv *.webm"),
    ("All files", "*.*"),
]


def pick_video_file(exercise_name):
    """Open a file dialog (tkinter ships with Python). Returns a path or None."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("tkinter is not available. Use: python main.py --video path\\to\\video.mp4")
        return None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        parent=root, title=f"Select a video to analyze ({exercise_name})", filetypes=VIDEO_TYPES
    )
    root.destroy()
    return path or None


def _fit_frame(frame):
    """Scale a video frame to fit inside the 960x540 canvas (keeps the aspect ratio)."""
    h, w = frame.shape[:2]
    scale = min(CANVAS_W / w, CANVAS_H / h)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=interp)


def _to_canvas(fit):
    """Center the frame on a black 960x540 canvas so the HUD layout is always the same."""
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8)
    h, w = fit.shape[:2]
    y0, x0 = (CANVAS_H - h) // 2, (CANVAS_W - w) // 2
    canvas[y0:y0 + h, x0:x0 + w] = fit
    return canvas


def _draw_video_hud(frame, name, exercise, state, t, duration, progress, status):
    h, w = frame.shape[:2]

    panel(frame, 15, 15, 300, 275)
    text(frame, exercise.upper(), (30, 50), 0.9, GREY)
    text(frame, "REPS", (30, 82), 0.6, GREY, 1)
    text(frame, str(state.count), (30, 158), 2.8, WHITE, 5)
    clock = fmt_time(t) + (f" / {fmt_time(duration)}" if duration else "")
    text(frame, clock, (30, 198), 0.8, GREEN)
    if state.angle is not None:
        text(frame, f"Joint angle: {int(state.angle)} deg", (30, 228), 0.5, GREY, 1)
    text(frame, f"Half reps: {state.half_reps}", (30, 255), 0.5, ORANGE if state.half_reps else GREY, 1)

    text(frame, "VIDEO ANALYSIS", (315, 40), 0.8, WHITE)
    shown = name if len(name) <= 45 else name[:42] + "..."
    text(frame, shown, (315, 64), 0.5, GREY, 1)
    cv2.rectangle(frame, (315, 78), (945, 90), WHITE, 1)
    cv2.rectangle(frame, (316, 79), (316 + int(628 * progress), 89), GREEN, -1)
    if status:
        text(frame, status, (315, 120), 0.7, ORANGE, 2)

    panel(frame, 15, h - 120, w - 15, h - 15)
    text(frame, state.feedback, (35, h - 70), 1.1, GREEN if state.feedback_ok else ORANGE, 3)
    text(frame, "SPACE pause   T fast-forward   Q finish and show results", (35, h - 32), 0.5, GREY, 1)


def analyze_video(path, exercise_name, window):
    """Play and analyze the video. Returns (results or None, window_still_open)."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"Could not open the video: {path}")
        print("Tip: use an .mp4 (H.264) file; if the path contains non-English characters, "
              "copy the video to a simple path such as C:\\videos\\test.mp4 and try again.")
        return None, True

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps or fps < 1 or fps > 240:
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_total = total_frames / fps if total_frames > 0 else 0

    # A fresh estimator: MediaPipe needs timestamps that start from 0 for each video.
    estimator = PoseEstimator()
    counter = EXERCISES[exercise_name]()
    name = os.path.basename(path)

    frame_idx = pose_frames = 0
    t = 0.0
    paused = fast = False
    window_open = True
    canvas = None
    state = None
    play_start = time.time()

    try:
        while True:
            if not paused:
                ok, frame = cap.read()
                if not ok:
                    break  # end of the video
                t = frame_idx / fps
                fit = _fit_frame(frame)
                landmarks = estimator.detect(fit, t * 1000)
                draw_skeleton(fit, landmarks)
                state = counter.update(landmarks, t)
                frame_idx += 1
                if landmarks is not None:
                    pose_frames += 1
                canvas = _to_canvas(fit)

            view = canvas.copy()
            progress = min(1.0, frame_idx / total_frames) if total_frames > 0 else 0.0
            status = "PAUSED" if paused else ("FAST-FORWARD" if fast else "")
            _draw_video_hud(view, name, exercise_name, state, t, duration_total, progress, status)
            cv2.imshow(window, view)

            if paused:
                wait = 30
            elif fast:
                wait = 1
            else:  # keep real-time speed: show frame k at play_start + k / fps
                wait = max(1, int((play_start + frame_idx / fps - time.time()) * 1000))
            key = cv2.waitKey(min(wait, 1000)) & 0xFF

            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                window_open = False
                break
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                paused = not paused
                play_start = time.time() - frame_idx / fps
            elif key == ord("t"):
                fast = not fast
                play_start = time.time() - frame_idx / fps
    finally:
        estimator.close()
        cap.release()

    if not window_open:
        return None, False
    if frame_idx == 0:
        print("The video contained no readable frames.")
        return None, True

    counter.finish(t)
    results = {
        "video_name": name,
        "video_path": path,
        "duration": frame_idx / fps,
        "pose_pct": 100.0 * pose_frames / frame_idx,
        "summary": counter.summary(),
    }
    return results, True


def run_video_analysis(path, exercise_name, window, store=None, profile_id=None):
    """Analyze a video, save it to the profile (if one is selected) and show the results.
    Returns False if the window was closed."""
    results, window_open = analyze_video(path, exercise_name, window)
    if results is not None and window_open:
        record_results(store, profile_id, results, "free", "video")
        return show_results(window, results)
    return window_open