# AI Pose Trainer

A small computer-vision demo for a Physical Education course. It uses MediaPipe Pose to
track the body, draw a skeleton, count repetitions of **squats** and **push-ups**, and give
simple posture feedback. It works live with a webcam and on **recorded videos**.

> Educational demonstration only. The feedback is simple rule-based geometry and is
> **not** a medical or injury assessment.

## Features

- Real-time skeleton overlay on the webcam feed
- Squat and push-up repetition counting with rule-based feedback
  ("Go lower", "Keep your chest up", "Keep your body aligned", ...)
- Clickable buttons (Squat, Push-up, Start/Stop, Reset, Video) and keyboard shortcuts
- 3-second countdown, session timer, separate counter per exercise
- Green flash and beep on every counted rep, fullscreen mode
- **Video analysis:** open a recorded video, watch the reps being counted as it plays,
  then see a results screen with detailed statistics
- Runs locally on CPU, offline after the first start

## Installation (Windows 10, Python 3.12)

```
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

Live webcam:

```
python app.py
```

Analyze a recorded video without a webcam:

```
python app.py --video C:\videos\my_squats.mp4 --exercise squat
python app.py --video C:\videos\my_pushups.mp4 --exercise push-up
```

On the first run the app downloads the pose model (~5 MB) into the `models/` folder.
After that it works fully offline. If the download fails, the error message shows
the URL and where to save the file manually.

If the wrong camera opens, try `python app.py --camera 1`.

## Controls (live mode)

| Key | Mouse button | Action |
|---|---|---|
| SPACE | Start / Stop | Start or stop the session (3-second countdown on start) |
| R | Reset | Reset all counters and the timer |
| 1 / 2 | Squat / Push-up | Select the exercise |
| O | Video | Choose a recorded video and analyze it with the selected exercise |
| F | - | Fullscreen on/off |
| M | - | Sound on/off |
| Q / ESC | - | Quit |

## Video analysis

1. Select **Squat** or **Push-up**, then click **Video** (or press `O`) and choose a file.
   (Or use the `--video` command-line option above.)
2. The video plays at normal speed with the skeleton and a live rep counter.
   - SPACE: pause / resume
   - T: fast-forward on/off (processes as fast as possible)
   - Q / ESC: stop early and show the results
3. At the end the **results screen** appears. Press `S` to save it as a PNG next to the
   video, and ENTER to close it (back to live mode).

### What the results screen shows

| Item | Meaning |
|---|---|
| Full reps counted | Reps that reached full depth and returned to the top |
| Half reps (not counted) | Clear attempts that went down but did not reach full depth, plus a movement still unfinished when the video ended |
| Rep completion rate | Full reps divided by all attempts (full + half) |
| Reps with good form / form warnings | Full reps where no warning ("Keep your chest up" / "Keep your body aligned") appeared during the rep |
| Video length, reps per minute | Reps per minute is measured over the whole video |
| Average / fastest / slowest rep time | Time from starting to go down until back at the top |
| Average / deepest depth | Smallest joint angle reached per rep (smaller = deeper) |
| Body tracked in | Share of frames where a person was detected (a quality check) |
| Chart | One bar per attempt: green = full rep, yellow = full rep with form warning, red = half rep. The dashed line is the depth needed for a full rep |

Tiny wobbles (a very small knee or elbow bend) are ignored and are not counted as half reps.

### Tips for recording a video

- Same camera tips as live mode: side view, whole body in frame, even lighting.
- Keep the camera still (a phone on a stand or a stack of books works well).
- Use `.mp4` (H.264). Phone videos in portrait or landscape both work.
- If the video does not open and its path contains non-English characters, copy it to a
  simple path such as `C:\videos\test.mp4`.

## How to do a squat

![Squat demonstration](images/squat.svg)

## How to do a push-up

![Push-up demonstration](images/pushup.svg)

## How the counting works

Each exercise uses one joint angle that is smoothed and run through a small state machine.
A repetition counts when you reach the bottom position and return to the top.

| Exercise | Joint angle | Bottom | Top | Extra feedback |
|---|---|---|---|---|
| Squat | knee (hip-knee-ankle) | below 100 deg | above 160 deg | torso lean ("Keep your chest up") |
| Push-up | elbow (shoulder-elbow-wrist) | below 95 deg | above 155 deg | body line shoulder-hip-ankle ("Keep your body aligned") |

Push-ups are only counted while the body is roughly horizontal, so standing up or walking
around never adds repetitions.

## Camera setup tips

- **Squats:** stand sideways (or at about 45 degrees) to the camera with hips, knees and ankles visible.
- **Push-ups:** place the camera at floor level, about 2-3 m away, and lie sideways to it so the whole body is in frame.
- Keep your whole body in the picture, use even lighting, and avoid strong backlight (a window behind you).
- Wear clothes that contrast with the background.

## Known limitations

- Accuracy drops when facing the camera directly (squats) or when limbs are hidden.
- Only one person is tracked.
- Very fast movements can cause missed counts.
- The body-alignment check cannot tell a sagging hip from a raised hip; it only reports "Keep your body aligned".
- Thresholds are fixed and may need adjusting for different people or camera angles.
- Half-rep and form statistics depend on the same rough thresholds, so treat them as indicators, not exact measurements.
- On-screen text supports English characters only (file names with other scripts show as "?").

## Project structure

```
app.py              OpenCV window, buttons, HUD, live loop, command-line options
pose_estimator.py   MediaPipe PoseLandmarker wrapper + skeleton drawing
exercises.py        Angle math, squat and push-up state machines, feedback, rep statistics
video_analyzer.py   Plays and analyzes a recorded video, file picker
results_screen.py   Results screen (statistics + chart), save as PNG
ui.py               Shared drawing helpers
requirements.txt
images/             squat.svg, pushup.svg (illustrations used in this README)
```

## Credits

- MediaPipe Pose Landmarker (Google, Apache 2.0)
- OpenCV