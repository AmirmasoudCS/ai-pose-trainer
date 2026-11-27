"""Small drawing helpers shared by the live app, the video analyzer and the results screen."""
import cv2

WHITE = (255, 255, 255)
GREEN = (120, 220, 90)
ORANGE = (60, 160, 255)
YELLOW = (60, 200, 240)
RED = (80, 80, 230)
GREY = (200, 200, 200)

BTN_IDLE = (70, 70, 70)
BTN_ACTIVE = (200, 130, 30)
BTN_START = (80, 170, 60)
BTN_STOP = (60, 80, 210)


def fmt_time(seconds):
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def panel(frame, x1, y1, x2, y2, alpha=0.55):
    """Draw a semi-transparent dark rectangle."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (30, 30, 30), -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def text(frame, msg, pos, scale=0.8, color=WHITE, thickness=2):
    cv2.putText(frame, msg, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def text_width(msg, scale=0.8, thickness=2):
    (tw, _th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    return tw


def draw_buttons(frame, buttons):
    """buttons: list of (label, (x1, y1, x2, y2), action, color)."""
    for label, (x1, y1, x2, y2), _action, color in buttons:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, -1)
        cv2.rectangle(frame, (x1, y1), (x2, y2), WHITE, 1)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        text(frame, label, (x1 + (x2 - x1 - tw) // 2, y1 + (y2 - y1 + th) // 2), 0.7)