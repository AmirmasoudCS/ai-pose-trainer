"""Progress screen: statistics and a chart of one profile's workouts over time.

Keys: E = next exercise, M = next mode filter, ENTER / ESC / Q = close.
"""
import math
from datetime import datetime

import cv2
import numpy as np

from exercises import EXERCISES
from profiles import mode_label
from ui import GREEN, GREY, ORANGE, WHITE, YELLOW, ascii_text, panel, text, text_width

W, H = 960, 540
MODE_FILTERS = [None, "free", "30s", "60s"]   # None = all modes
CHART_MAX_POINTS = 20


def _mean(values):
    return sum(values) / len(values) if values else None


def _date(record, fmt="%m-%d"):
    try:
        return datetime.fromisoformat(record["date"]).strftime(fmt)
    except (KeyError, ValueError):
        return "?"


def _stat_rows(records):
    reps = [r.get("reps", 0) for r in records]
    total = sum(reps)
    best = max(reps)
    best_record = records[reps.index(best)]
    change = reps[-1] - reps[0]
    avg_time = _mean([r["avg_rep_time"] for r in records if r.get("avg_rep_time")])
    avg_depth = _mean([r["avg_depth"] for r in records if r.get("avg_depth") is not None])
    good = sum(r.get("good_form_reps", 0) for r in records)

    if len(records) > 1:
        trend = f"{reps[0]} -> {reps[-1]} ({change:+d})"
        trend_color = GREEN if change > 0 else (ORANGE if change < 0 else WHITE)
    else:
        trend, trend_color = "only one workout so far", GREY

    return [
        ("Workouts", str(len(records)), WHITE),
        ("Total reps", str(total), WHITE),
        ("Personal best", f"{best} reps ({_date(best_record)})", YELLOW),
        ("Average reps per workout", f"{total / len(records):.1f}", WHITE),
        ("First -> latest workout", trend, trend_color),
        ("Average time per rep", "-" if avg_time is None else f"{avg_time:.1f} s", WHITE),
        ("Average depth (joint angle)", "-" if avg_depth is None else f"{avg_depth:.0f} deg", WHITE),
        ("Reps with good form", f"{good / total * 100:.0f}%" if total else "-", WHITE),
    ]


def _draw_chart(img, records):
    x0, x1, y_top, y_bot = 535, 915, 150, 430
    text(img, "Reps per workout", (510, 122), 0.7, WHITE, 2)
    if not records:
        text(img, "No workouts recorded yet", (x0, 270), 0.7, ORANGE, 2)
        text(img, "for this selection.", (x0, 300), 0.7, ORANGE, 2)
        text(img, "Finish a session to see your progress here.", (x0, 340), 0.5, GREY, 1)
        return

    shown = records[-CHART_MAX_POINTS:]
    text(img, f"latest {len(shown)} of {len(records)} workouts", (510, 142), 0.45, GREY, 1)

    top = max(6, math.ceil(max(r.get("reps", 0) for r in shown) * 1.15 / 2) * 2)  # even: clean mid grid line
    height = y_bot - y_top
    for frac in (0, 0.5, 1):  # grid lines + labels
        y = int(y_bot - frac * height)
        cv2.line(img, (x0, y), (x1, y), (80, 80, 80), 1)
        label = str(round(top * frac))
        text(img, label, (x0 - 8 - text_width(label, 0.4, 1), y + 5), 0.4, GREY, 1)

    n = len(shown)
    xs = [int((x0 + x1) / 2)] if n == 1 else [int(x0 + 20 + (x1 - x0 - 40) * i / (n - 1)) for i in range(n)]
    ys = [int(y_bot - r.get("reps", 0) / top * height) for r in shown]
    for i in range(1, n):
        cv2.line(img, (xs[i - 1], ys[i - 1]), (xs[i], ys[i]), GREEN, 2, cv2.LINE_AA)

    best_i = max(range(n), key=lambda i: shown[i].get("reps", 0))
    every = max(1, math.ceil(n / 8))  # at most ~8 date labels
    labeled = set(range(0, n, every))
    if (n - 1) - max(labeled) >= 2:   # also label the latest workout unless it would crowd
        labeled.add(n - 1)
    for i, r in enumerate(shown):
        is_best = i == best_i
        cv2.circle(img, (xs[i], ys[i]), 8 if is_best else 5, YELLOW if is_best else GREEN, -1, cv2.LINE_AA)
        if n <= 12:
            label = str(r.get("reps", 0))
            text(img, label, (xs[i] - text_width(label, 0.45, 1) // 2, ys[i] - 14), 0.45, WHITE, 1)
        if i in labeled:
            label = _date(r)
            text(img, label, (xs[i] - text_width(label, 0.4, 1) // 2, y_bot + 20), 0.4, GREY, 1)

    cv2.circle(img, (515, 462), 6, YELLOW, -1, cv2.LINE_AA)
    text(img, "personal best in this view", (528, 467), 0.45, GREY, 1)


def draw_progress(store, profile_id, exercise, mode, message=""):
    img = np.full((H, W, 3), (38, 38, 38), np.uint8)
    profile = store.get(profile_id)
    name = ascii_text(profile["name"]).upper() if profile else "?"
    records = store.records(profile_id, exercise, mode)

    text(img, f"PROGRESS - {name}", (30, 48), 1.1, WHITE, 3)
    mode_text = "All modes" if mode is None else mode_label(mode)
    text(img, f"Exercise: {exercise} (E)     Mode: {mode_text} (M)", (30, 76), 0.55, GREY, 1)

    # Left: statistics + recent sessions
    panel(img, 20, 90, 470, 495, alpha=0.5)
    if records:
        y = 122
        for label, value, color in _stat_rows(records):
            text(img, label, (40, y), 0.55, GREY, 1)
            text(img, value, (450 - text_width(value, 0.6, 2), y), 0.6, color, 2)
            y += 28
        text(img, "Recent sessions", (40, 365), 0.55, WHITE, 1)
        y = 392
        for r in reversed(records[-4:]):
            text(img, f"{_date(r, '%m-%d %H:%M')}", (40, y), 0.48, GREY, 1)
            text(img, mode_label(r.get("mode", "")), (170, y), 0.48, GREY, 1)
            text(img, f"{r.get('reps', 0)} reps", (240, y), 0.48, WHITE, 1)
            text(img, f"{r.get('half_reps', 0)} half", (330, y), 0.48, GREY, 1)
            text(img, "video" if r.get("source") == "video" else "live", (410, y), 0.48, GREY, 1)
            y += 24
    else:
        text(img, "No workouts recorded yet", (40, 250), 0.7, ORANGE, 2)
        text(img, "for this exercise and mode.", (40, 282), 0.7, ORANGE, 2)

    panel(img, 490, 90, 940, 495, alpha=0.5)
    _draw_chart(img, records)

    text(img, "Educational demo - not a medical assessment.", (30, 522), 0.45, GREY, 1)
    hint = "E exercise   M mode   ENTER close"
    text(img, hint, (W - 30 - text_width(hint, 0.5, 1), 522), 0.5, GREY, 1)
    return img


def show_progress(window, store, profile_id, exercise_name, mode=None):
    """Show the progress screen until closed. Returns False if the window was closed."""
    names = list(EXERCISES)
    ex_i = names.index(exercise_name) if exercise_name in names else 0
    mode_i = MODE_FILTERS.index(mode) if mode in MODE_FILTERS else 0
    while True:
        img = draw_progress(store, profile_id, names[ex_i], MODE_FILTERS[mode_i])
        cv2.imshow(window, img)
        key = cv2.waitKey(50) & 0xFF
        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            return False
        if key == ord("e"):
            ex_i = (ex_i + 1) % len(names)
        elif key == ord("m"):
            mode_i = (mode_i + 1) % len(MODE_FILTERS)
        elif key in (13, 27, ord("q"), ord(" ")):
            return True