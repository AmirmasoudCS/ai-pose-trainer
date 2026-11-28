# AI Pose Trainer - web app

The same idea as the desktop app, running in the browser on your laptop **and your phone**.
Pose detection (MediaPipe) and rep counting run on your own device: there is no backend,
and your video is never uploaded.

> Educational demonstration only. The feedback is simple rule-based geometry and is
> **not** a medical or injury assessment.

## Status

| Phase | Content | State |
|---|---|---|
| 1 | Camera, skeleton, squat and push-up counting, timer, feedback | done |
| 2 | Free / 30 s / 60 s modes and a results screen | planned |
| 3 | Profiles and progress charts | planned |
| 4 | Analyze a recorded video file | planned |
| 5 | Install on the phone, works offline | planned |

## Run it on your laptop

The camera only works on `https://` pages or on `localhost`, so open the page through a
small local server (double-clicking `index.html` will not work):

```
cd web
python -m http.server 8000
```

Then open <http://localhost:8000> in Chrome, Edge, Firefox or Safari and click **Start camera**.
The first start downloads the pose model (about 6 MB) and needs the internet.

## Run it on your phone (free hosting, HTTPS included)

Phones refuse camera access on plain `http://` addresses, so the easiest way is to publish
the site with GitHub Pages:

1. Push the repository to GitHub (branch `main`).
2. On GitHub open **Settings -> Pages** and set **Source** to **GitHub Actions**.
3. The workflow `.github/workflows/pages.yml` runs the tests and publishes the `web/` folder.
   Check progress in the **Actions** tab. You can also start it manually with **Run workflow**.
4. Your site is at `https://<your-username>.github.io/<repository-name>/`.
5. Open that link on your phone and allow the camera.

Every push that changes `web/` republishes the site automatically.

## Using it

1. Tap **Start camera** (the first time, the model downloads).
2. Choose **Squat** or **Push-up**, prop the device up, and step back until your whole body is visible.
3. Tap **Start**. After a 3-second countdown reps are counted, with a beep and a short vibration (Android) on each one.
4. **Stop** ends the session, **Reset** clears it, **Flip camera** switches between front and back cameras.

Camera tips: squats from the side or at about 45 degrees; push-ups with the phone on the floor
2-3 m away, lying sideways to it. Keep the device still and avoid a bright window behind you.

## Tests

The counting logic is a direct port of `pose_trainer/core/exercises.py` and is tested without
a camera (Node 20 or newer):

```
cd web
node --test
```

## Files

```
web/
├── index.html           the page
├── css/style.css        mobile-first dark theme
├── js/
│   ├── main.js          camera, main loop, buttons, on-screen display
│   ├── pose.js          loads MediaPipe PoseLandmarker (pinned version, from a CDN)
│   ├── exercises.js     angles, squat / push-up rules, rep statistics
│   └── draw.js          skeleton drawing
└── tests/exercises.test.mjs
```

## Known limitations

- The first visit needs the internet (model and library are downloaded). Offline use comes in Phase 5.
- Speed depends on the device. Recent phones run the lite model smoothly; older ones may show a lower FPS.
- Same accuracy limits as the desktop app: side view works best, only one person is tracked.
- Browsers can ask again for the camera permission each visit unless the site is allowed permanently.