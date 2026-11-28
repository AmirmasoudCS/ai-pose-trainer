"""Results screen shown after a video has been analyzed.

`results` is a dict made by video_analyzer.analyze_video():
  video_name, video_path, duration (seconds), pose_pct, summary (Exercise.summary())
"""
import os

import cv2
import numpy as np

from ui import GREEN, GREY, ORANGE, RED, WHITE, YELLOW, ascii_text, fmt_time, panel, text, text_width

W, H = 960, 540
CHART_MAX_BARS = 30
CHART_SCALE_DEG = 120  # a bar of this height = 120 degrees of bend (fully folded joint)


def _sec(value):
    return "-" if value is None else f"{value:.1f} s"


def _deg(value):
    return "-" if value is None else f"{value:.0f} deg"


def _rows(results):
    s = results["summary"]
    reps, half = s["reps"], s["half_reps"]
    duration = results["duration"]
    attempts = reps + half
    rate = f"{reps / attempts * 100:.0f}%" if attempts else "-"
    rpm = f"{reps / duration * 60:.1f}" if duration > 0 else "-"
    fast_slow = "-" if s["fastest_rep"] is None else f"{s['fastest_rep']:.1f} / {s['slowest_rep']:.1f} s"
    return [
        ("Full reps counted", str(reps), GREEN),
        ("Half reps (not counted)", str(half), ORANGE if half else WHITE),
        ("Rep completion rate", rate, WHITE),
        ("Reps with good form", f"{s['good_form_reps']} of {reps}", WHITE),
        ("Reps with form warnings", str(s["form_issue_reps"]), YELLOW if s["form_issue_reps"] else WHITE),
        (results.get("length_label", "Video length"), fmt_time(duration), WHITE),
        ("Reps per minute", rpm, WHITE),
        ("Average time per rep", _sec(s["avg_rep_time"]), WHITE),
        ("Fastest / slowest rep", fast_slow, WHITE),
        ("Average depth (joint angle)", _deg(s["avg_depth"]), WHITE),
        ("Deepest rep (joint angle)", _deg(s["best_depth"]), WHITE),
        ("Body tracked in", f"{results['pose_pct']:.0f}% of frames", WHITE),
    ]


def _draw_chart(img, s):
    x0, x1, y_top, y_bot = 515, 920, 150, 430
    text(img, "Depth per attempt", (510, 122), 0.7, WHITE, 2)
    text(img, "taller = deeper  |  dashed line = depth for a full rep", (510, 142), 0.45, GREY, 1)
    cv2.line(img, (x0, y_bot), (x1, y_bot), GREY, 1)

    attempts = s["attempts"][:CHART_MAX_BARS]
    if not attempts:
        text(img, "No repetitions detected.", (x0, 280), 0.7, ORANGE, 2)
        text(img, "Check the camera angle and that the", (x0, 315), 0.5, GREY, 1)
        text(img, "whole body is visible in the video.", (x0, 337), 0.5, GREY, 1)
        return

    height = y_bot - y_top
    n = len(attempts)
    step = (x1 - x0) / n
    bar_w = max(4, int(min(36, step * 0.7)))

    for i, a in enumerate(attempts):
        depth = max(0.0, min(CHART_SCALE_DEG, 180 - a["min_angle"]))
        bar_h = max(3, int(depth / CHART_SCALE_DEG * height))
        cx = int(x0 + step * (i + 0.5))
        color = RED if not a["full"] else (YELLOW if a["form_issue"] else GREEN)
        cv2.rectangle(img, (cx - bar_w // 2, y_bot - bar_h), (cx + bar_w // 2, y_bot), color, -1)
        if n <= 20:
            label = str(i + 1)
            text(img, label, (cx - text_width(label, 0.4, 1) // 2, y_bot + 18), 0.4, GREY, 1)

    # Dashed line = depth needed for a full rep (drawn over the bars)
    y_thr = int(y_bot - (180 - s["down_angle"]) / CHART_SCALE_DEG * height)
    for x in range(x0, x1, 14):
        cv2.line(img, (x, y_thr), (min(x + 7, x1), y_thr), WHITE, 2)

    if len(s["attempts"]) > CHART_MAX_BARS:
        text(img, f"(first {CHART_MAX_BARS} of {len(s['attempts'])} attempts)", (x0, y_bot + 18), 0.4, GREY, 1)

    # Legend
    x = 515
    for color, label in ((GREEN, "full rep"), (YELLOW, "full rep, form warning"), (RED, "half rep")):
        cv2.rectangle(img, (x, 455), (x + 14, 469), color, -1)
        text(img, label, (x + 22, 468), 0.45, GREY, 1)
        x += 30 + text_width(label, 0.45, 1) + 22


def draw_results(results, message=""):
    img = np.full((H, W, 3), (38, 38, 38), np.uint8)
    s = results["summary"]

    title = f"RESULTS - {s['exercise'].upper()}"
    if results.get("mode_label"):
        title += f" ({results['mode_label']})"
    text(img, title, (30, 48), 1.1, WHITE, 3)
    text(img, ascii_text(results["video_name"]), (30, 74), 0.5, GREY, 1)
    note = results.get("note")
    if note:
        kind = results.get("note_kind")
        color = {"best": YELLOW, "warn": ORANGE}.get(kind, GREEN)
        scale = 0.8 if kind == "best" else 0.55
        note = ascii_text(note)
        text(img, note, (W - 30 - text_width(note, scale, 2), 74), scale, color, 2)

    panel(img, 20, 90, 470, 495, alpha=0.5)
    y = 125
    for i, (label, value, color) in enumerate(_rows(results)):
        text(img, label, (40, y), 0.6, GREY, 1)
        scale, thick = (1.0, 2) if i == 0 else (0.65, 2)
        text(img, value, (450 - text_width(value, scale, thick), y), scale, color, thick)
        y += 30

    panel(img, 490, 90, 940, 495, alpha=0.5)
    _draw_chart(img, s)

    text(img, "Educational demo - not a medical assessment.", (30, 522), 0.45, GREY, 1)
    hint = message or "S save image   ENTER close"
    text(img, hint, (W - 30 - text_width(hint, 0.5, 1), 522), 0.5, GREEN if message else GREY, 1)
    return img


def save_results_image(results, img):
    """Save next to the video / in data/results. Returns the saved path or None."""
    base = results.get("image_base") or os.path.splitext(results.get("video_path", "results"))[0]
    ok, buf = cv2.imencode(".png", img)  # imencode + file write also works with non-ASCII paths
    if not ok:
        return None
    for path in (base + "_results.png", os.path.basename(base) + "_results.png"):
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(buf.tobytes())
            return path
        except OSError:
            continue
    return None


def show_results(window, results):
    """Show the results until the user closes them. Returns False if the window was closed."""
    message = ""
    while True:
        img = draw_results(results, message)
        cv2.imshow(window, img)
        key = cv2.waitKey(50) & 0xFF
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return False
        if key == ord("s"):
            path = save_results_image(results, img)
            message = f"Saved: {os.path.basename(path)}" if path else "Could not save the image"
        elif key in (13, 27, ord("q"), ord(" ")):
            return True