/**
 * AI Pose Trainer (web): camera -> pose landmarks -> rep counting, all in the browser.
 *
 * Phase 1: camera, skeleton, squat and push-up counting, session timer, feedback.
 */
import { drawSkeleton } from "./draw.js";
import { EXERCISES } from "./exercises.js";
import { PoseDetector } from "./pose.js";

const COUNTDOWN_SECONDS = 3;
const $ = (id) => document.getElementById(id);

const el = {
  stage: $("stage"),
  video: $("video"),
  canvas: $("overlay"),
  hud: $("hud"),
  reps: $("reps"),
  clock: $("clock"),
  clockLabel: $("clock-label"),
  countdown: $("countdown"),
  feedback: $("feedback"),
  splash: $("splash"),
  splashError: $("splash-error"),
  status: $("status"),
  picker: $("exercise-picker"),
  btnCamera: $("btn-camera"),
  btnStart: $("btn-start"),
  btnReset: $("btn-reset"),
  btnFlip: $("btn-flip"),
  btnSound: $("btn-sound"),
  halfReps: $("half-reps"),
  formWarnings: $("form-warnings"),
  angle: $("angle"),
  fps: $("fps"),
};
const ctx = el.canvas.getContext("2d");

const app = {
  detector: null,
  stream: null,
  facing: "user",
  exerciseName: Object.keys(EXERCISES)[0],
  counter: null,
  running: false, // a session is active (countdown or counting)
  runStart: 0, // seconds (performance clock) when counting begins
  lastElapsed: 0,
  seenCount: 0,
  muted: false,
  audio: null,
  wakeLock: null,
  lastVideoTime: -1,
  lastFrameMs: 0,
  fps: 0,
  flashTimer: null,
};
app.counter = new EXERCISES[app.exerciseName]();

// ---- small helpers -----------------------------------------------------------
/** Update text only when it changed (avoids needless layout work every frame). */
function setText(node, value) {
  const text = String(value);
  if (node._text !== text) {
    node.textContent = text;
    node._text = text;
  }
}
const fmtTime = (seconds) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const nowSeconds = () => performance.now() / 1000;

function setStatus(message) {
  setText(el.status, message);
}

// ---- exercise picker ---------------------------------------------------------
function buildPicker() {
  el.picker.replaceChildren();
  for (const name of Object.keys(EXERCISES)) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.textContent = name;
    button.dataset.exercise = name;
    button.setAttribute("aria-checked", String(name === app.exerciseName));
    button.addEventListener("click", () => selectExercise(name));
    el.picker.append(button);
  }
}

function selectExercise(name) {
  if (app.running || name === app.exerciseName) return;
  app.exerciseName = name;
  app.counter = new EXERCISES[name]();
  app.seenCount = 0;
  app.lastElapsed = 0;
  for (const button of el.picker.children) {
    button.setAttribute("aria-checked", String(button.dataset.exercise === name));
  }
}

// ---- camera ------------------------------------------------------------------
function explainCameraError(error) {
  switch (error && error.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera permission was denied. Allow the camera for this site in your browser settings and try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device.";
    case "NotReadableError":
      return "The camera is being used by another app. Close it and try again.";
    case "NotSupportedError":
      return "This browser cannot use the camera here. Try the latest Chrome, Edge, Firefox or Safari.";
    default:
      return `Could not start the camera (${(error && error.message) || error}).`;
  }
}

async function openStream(facing) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false,
  });
  if (app.stream) app.stream.getTracks().forEach((track) => track.stop());
  app.stream = stream;
  el.video.srcObject = stream;
  await el.video.play();
  if (!el.video.videoWidth) {
    await new Promise((resolve) => el.video.addEventListener("loadedmetadata", resolve, { once: true }));
  }

  const { videoWidth: w, videoHeight: h } = el.video;
  el.canvas.width = w;
  el.canvas.height = h;
  el.stage.style.setProperty("--ratio", `${w} / ${h}`);
  el.stage.style.setProperty("--ratio-num", String(w / h));

  const reported = stream.getVideoTracks()[0].getSettings().facingMode;
  el.stage.classList.toggle("mirrored", (reported || facing) !== "environment"); // selfie view
  app.facing = facing;
  app.lastVideoTime = -1;
}

async function enableCamera() {
  el.splashError.textContent = "";
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    el.splashError.textContent =
      "This page needs a secure connection (https) to use the camera. Open the https link of the site.";
    return;
  }
  el.btnCamera.disabled = true;
  el.btnCamera.textContent = "Loading...";

  // Audio can only start after a tap, so prepare it here.
  try {
    app.audio = app.audio || new (window.AudioContext || window.webkitAudioContext)();
  } catch (_error) {
    app.audio = null;
  }

  try {
    if (!app.detector) {
      setStatus("Loading model...");
      try {
        app.detector = await PoseDetector.create();
      } catch (error) {
        throw Object.assign(new Error("model"), { cause: error, isModelError: true });
      }
    }
    await openStream(app.facing);
  } catch (error) {
    el.splashError.textContent = error.isModelError
      ? "Could not load the pose model. Check your internet connection (it is needed the first time)."
      : explainCameraError(error);
    el.btnCamera.disabled = false;
    el.btnCamera.textContent = "Try again";
    setStatus("Camera off");
    return;
  }

  el.splash.hidden = true;
  el.hud.hidden = false;
  for (const button of [el.btnStart, el.btnReset, el.btnFlip]) button.disabled = false;
  setStatus(`Ready (${app.detector.delegate})`);
  requestAnimationFrame(loop);
}

async function flipCamera() {
  if (app.running) return;
  const previous = app.facing;
  el.btnFlip.disabled = true;
  try {
    await openStream(previous === "user" ? "environment" : "user");
  } catch (error) {
    setStatus("Could not switch camera");
    try {
      await openStream(previous);
    } catch (_ignored) {
      /* keep whatever stream we had */
    }
  } finally {
    el.btnFlip.disabled = false;
  }
}

// ---- session -----------------------------------------------------------------
async function keepScreenAwake(on) {
  try {
    if (on && "wakeLock" in navigator) {
      app.wakeLock = await navigator.wakeLock.request("screen");
    } else if (app.wakeLock) {
      await app.wakeLock.release();
      app.wakeLock = null;
    }
  } catch (_error) {
    /* not supported or refused: not important */
  }
}

function startSession() {
  app.counter.reset();
  app.seenCount = 0;
  app.lastElapsed = 0;
  app.runStart = nowSeconds() + COUNTDOWN_SECONDS;
  app.running = true;
  keepScreenAwake(true);
  renderControls();
}

function stopSession() {
  const now = nowSeconds();
  app.lastElapsed = Math.max(0, now - app.runStart);
  app.running = false;
  app.counter.finish(now);
  keepScreenAwake(false);
  renderControls();
}

function resetSession() {
  if (app.running) {
    app.running = false;
    keepScreenAwake(false);
  }
  app.counter.reset();
  app.seenCount = 0;
  app.lastElapsed = 0;
  renderControls();
}

function renderControls() {
  el.btnStart.textContent = app.running ? "Stop" : "Start";
  el.btnStart.classList.toggle("stop", app.running);
  el.btnFlip.disabled = app.running;
  for (const button of el.picker.children) button.disabled = app.running;
}

// ---- feedback to the user ----------------------------------------------------
function beep() {
  if (app.muted || !app.audio) return;
  try {
    const osc = app.audio.createOscillator();
    const gain = app.audio.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(app.audio.destination);
    osc.start();
    osc.stop(app.audio.currentTime + 0.09);
  } catch (_error) {
    /* ignore audio problems */
  }
}

function celebrateRep() {
  beep();
  if (navigator.vibrate) navigator.vibrate(40);
  el.stage.classList.add("flash");
  clearTimeout(app.flashTimer);
  app.flashTimer = setTimeout(() => el.stage.classList.remove("flash"), 350);
}

// ---- main loop ---------------------------------------------------------------
function loop() {
  requestAnimationFrame(loop);
  const video = el.video;
  if (video.readyState < 2 || video.currentTime === app.lastVideoTime) return;
  app.lastVideoTime = video.currentTime;

  const nowMs = performance.now();
  const dt = nowMs - app.lastFrameMs;
  app.lastFrameMs = nowMs;
  if (dt > 0 && dt < 1000) app.fps = app.fps ? 0.9 * app.fps + 0.1 * (1000 / dt) : 1000 / dt;

  const landmarks = app.detector.detect(video, nowMs);
  drawSkeleton(ctx, landmarks, el.canvas.width, el.canvas.height);

  const now = nowMs / 1000;
  let state;
  if (app.running && now >= app.runStart) {
    state = app.counter.update(landmarks, now);
    if (state.count > app.seenCount) celebrateRep();
    app.seenCount = state.count;
  } else {
    state = {
      count: app.counter.count,
      angle: null,
      feedback: app.running ? "Get ready..." : "Press Start",
      feedbackOk: true,
    };
  }
  render(state, now);
}

function render(state, now) {
  setText(el.reps, state.count);
  setText(el.feedback, state.feedback);
  el.feedback.classList.toggle("warn", !state.feedbackOk);

  const counting = app.running && now >= app.runStart;
  const elapsed = counting ? now - app.runStart : app.lastElapsed;
  setText(el.clock, fmtTime(elapsed));
  setText(el.countdown, app.running && !counting ? Math.ceil(app.runStart - now) : "");

  const attempts = app.counter.attempts;
  setText(el.halfReps, attempts.filter((a) => !a.full).length);
  setText(el.formWarnings, attempts.filter((a) => a.full && a.formIssue).length);
  setText(el.angle, state.angle === null ? "-" : `${Math.round(state.angle)}\u00b0`);
  setText(el.fps, app.fps ? Math.round(app.fps) : "-");
}

// ---- wiring ------------------------------------------------------------------
buildPicker();
el.btnCamera.addEventListener("click", enableCamera);
el.btnStart.addEventListener("click", () => (app.running ? stopSession() : startSession()));
el.btnReset.addEventListener("click", resetSession);
el.btnFlip.addEventListener("click", flipCamera);
el.btnSound.addEventListener("click", () => {
  app.muted = !app.muted;
  el.btnSound.textContent = app.muted ? "Sound off" : "Sound on";
  el.btnSound.setAttribute("aria-pressed", String(!app.muted));
});