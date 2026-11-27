# AI Pose Trainer

A small computer-vision demo for a Physical Education course. It uses a webcam and
MediaPipe Pose to track the body, draw a skeleton, and count exercise repetitions.

> Educational demonstration only. The feedback is simple rule-based geometry and is
> **not** a medical or injury assessment.

## Current status

- Phase 2: webcam, real-time skeleton, squat counting (done)
- Phase 3 (planned): push-ups, extra feedback, exercise selection
- Phase 4 (planned): presentation-ready interface

## Installation (Windows 10, Python 3.12)

```
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```
python app.py
```

On the first run the app downloads the pose model (~5 MB) into the `models/` folder.
After that it works fully offline. If the download fails, the error message shows
the URL and where to save the file manually.

If the wrong camera opens, try `python app.py --camera 1`.

## Controls

| Key | Action |
|---|---|
| SPACE | Start / stop session |
| R | Reset counter and timer |
| 1 | Select Squat |
| Q / ESC | Quit |

## Tips for best results

- Stand sideways (or at about 45 degrees) to the camera so hip, knee and ankle are visible.
- Keep your whole body in the frame, with the camera about 2-3 m away.
- Use even lighting and avoid strong backlight (a window behind you).
- Wear clothes that contrast with the background.

## How the squat counter works

The knee angle (hip-knee-ankle) is smoothed and run through a small state machine:
standing is above 160 degrees, the bottom is below 100 degrees. A repetition counts when
you reach the bottom and return to standing. Shallow squats are not counted and show
"Go lower".

## Known limitations

- Accuracy drops when facing the camera directly.
- Only one person is tracked.
- Fast movements or partly hidden legs can cause missed or wrong counts.
- Thresholds are fixed and may need adjusting for different people or camera angles.

## Project structure

```
app.py              OpenCV window, HUD, keyboard controls
pose_estimator.py   MediaPipe PoseLandmarker wrapper + skeleton drawing
exercises.py        Angle math, squat state machine, feedback
requirements.txt
```

## Credits

- MediaPipe Pose Landmarker (Google, Apache 2.0)
- OpenCV