"""AI Personal Trainer - webcam demo (Phase 2: squat counter).

Controls:
  SPACE  start / stop session
  R      reset counter and timer
  1      select Squat
  Q/ESC  quit
"""
import argparse
import sys
import time

import cv2

from exercises import EXERCISES, RepState
from pose_estimator import PoseEstimator, draw_skeleton

FRAME_WIDTH = 960
WINDOW = "AI Personal Trainer"

WHITE = (255, 255, 255)
GREEN = (120, 220, 90)
ORANGE = (60, 160, 255)
GREY = (200, 200, 200)


def open_camera(index):
    # CAP_DSHOW starts much faster on Windows; fall back to the default backend.
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def fmt_time(seconds):
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def panel(frame, x1, y1, x2, y2, alpha=0.55):
    """Draw a semi-transparent dark rectangle."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (30, 30, 30), -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def text(frame, msg, pos, scale=0.8, color=WHITE, thickness=2):
    cv2.putText(frame, msg, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_hud(frame, exercise, state, elapsed, running):
    h, w = frame.shape[:2]

    # Top-left: exercise, reps, timer
    panel(frame, 15, 15, 300, 215)
    text(frame, exercise.upper(), (30, 50), 0.9, GREY)
    text(frame, "REPS", (30, 85), 0.6, GREY, 1)
    text(frame, str(state.count), (30, 160), 2.8, WHITE, 5)
    text(frame, fmt_time(elapsed), (30, 200), 0.8, GREEN if running else GREY)
    if state.angle is not None:
        text(frame, f"Angle: {int(state.angle)} deg", (150, 200), 0.55, GREY, 1)

    # Status badge
    badge, color = ("RECORDING", GREEN) if running else ("PAUSED", ORANGE)
    text(frame, badge, (w - 190, 40), 0.8, color)

    # Bottom: feedback + controls
    panel(frame, 15, h - 120, w - 15, h - 15)
    text(frame, state.feedback, (35, h - 70), 1.1, GREEN if state.feedback_ok else ORANGE, 3)
    text(frame, "SPACE start/stop   R reset   1 squat   Q quit", (35, h - 32), 0.55, GREY, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    args = parser.parse_args()

    cap = open_camera(args.camera)
    if not cap.isOpened():
        print("Could not open the webcam. Close other apps using it or try --camera 1.")
        return 1

    estimator = PoseEstimator()
    exercise_names = list(EXERCISES)
    exercise = exercise_names[0]
    counter = EXERCISES[exercise]()

    running = False
    run_start = 0.0
    elapsed_before = 0.0
    t0 = time.time()

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Lost the camera feed.")
                break

            frame = cv2.flip(frame, 1)  # mirror view feels natural
            scale = FRAME_WIDTH / frame.shape[1]
            frame = cv2.resize(frame, (FRAME_WIDTH, int(frame.shape[0] * scale)))

            landmarks = estimator.detect(frame, (time.time() - t0) * 1000)
            draw_skeleton(frame, landmarks)

            if running:
                state = counter.update(landmarks)
            else:
                state = RepState(counter.count, counter.stage, None, "Press SPACE to start", True)
            elapsed = elapsed_before + (time.time() - run_start if running else 0.0)

            draw_hud(frame, exercise, state, elapsed, running)
            cv2.imshow(WINDOW, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break  # window closed with the X button
            if key == ord(" "):
                if running:
                    elapsed_before += time.time() - run_start
                else:
                    run_start = time.time()
                running = not running
            elif key == ord("r"):
                counter.reset()
                elapsed_before = 0.0
                run_start = time.time()
            elif key == ord("1") and "Squat" in EXERCISES:
                exercise = "Squat"
                counter = EXERCISES[exercise]()
    finally:
        estimator.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())