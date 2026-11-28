// Tests for the counting logic using simulated body landmarks (no camera needed).
// Run from the web/ folder:   node --test
import assert from "node:assert/strict";
import { test } from "node:test";

import { PushUpCounter, SquatCounter, calculateAngle } from "../js/exercises.js";

const FPS = 30;

/** Side view: knee angle in degrees; `lean` shifts the shoulder forward (pixels). */
function squatLandmarks(kneeAngle, { lean = 0 } = {}) {
  const lm = Array.from({ length: 33 }, () => [0, 0, 0]);
  const t = (kneeAngle * Math.PI) / 180;
  const knee = [300, 300];
  const ankle = [300, 400];
  const hip = [300 + 100 * Math.sin(t), 300 + 100 * Math.cos(t)];
  const shoulder = [hip[0] + lean, hip[1] - 120];
  [[11, shoulder], [23, hip], [25, knee], [27, ankle]].forEach(([i, p]) => {
    lm[i] = [p[0], p[1], 0.99];
  });
  return lm;
}

/** Side view of a person in the push-up position (or standing). */
function pushupLandmarks(elbowAngle, { hipY = 310, standing = false } = {}) {
  const lm = Array.from({ length: 33 }, () => [0, 0, 0]);
  let points;
  if (standing) {
    points = { 11: [100, 100], 13: [100, 150], 15: [100, 200], 23: [100, 250], 25: [100, 350], 27: [100, 450] };
  } else {
    const offset = elbowAngle < 180 ? 40 / Math.tan((elbowAngle / 2) * (Math.PI / 180)) : 0;
    points = { 11: [100, 300], 13: [100 - offset, 340], 15: [100, 380], 23: [260, hipY], 25: [400, 320], 27: [540, 330] };
  }
  for (const [i, p] of Object.entries(points)) lm[i] = [p[0], p[1], 0.99];
  return lm;
}

function ramp(start, end, step = 5) {
  const n = Math.max(1, Math.trunc(Math.abs(end - start) / step));
  return Array.from({ length: n }, (_, i) => start + ((end - start) * (i + 1)) / n);
}

/** Feeds frames to a counter with video-style timestamps. */
class Clock {
  constructor(counter, makeLandmarks) {
    Object.assign(this, { counter, make: makeLandmarks, t: 0 });
  }
  frame(angle, options) {
    const state = this.counter.update(this.make(angle, options), this.t);
    this.t += 1 / FPS;
    return state;
  }
  rep(top, depth, options) {
    for (const angle of [...ramp(top, depth), ...ramp(depth, top)]) this.frame(angle, options);
  }
  idle(top, frames = 10) {
    for (let i = 0; i < frames; i++) this.frame(top);
  }
}

test("calculateAngle", () => {
  assert.equal(Math.round(calculateAngle([0, -1], [0, 0], [0, 1])), 180);
  assert.equal(Math.round(calculateAngle([1, 0], [0, 0], [0, 1])), 90);
});

test("squat counts deep reps only", () => {
  const c = new SquatCounter();
  const clock = new Clock(c, squatLandmarks);
  for (let i = 0; i < 3; i++) {
    clock.rep(175, 80);
    clock.idle(175);
  }
  assert.equal(c.count, 3);
  clock.rep(175, 118); // clear attempt, not deep enough
  assert.equal(c.count, 3);
  assert.equal(c.halfReps, 1);
});

test("a tiny wobble is not a half rep", () => {
  const c = new SquatCounter();
  new Clock(c, squatLandmarks).rep(175, 146);
  assert.equal(c.count, 0);
  assert.equal(c.halfReps, 0);
});

test("an unfinished movement becomes a half rep on finish()", () => {
  const c = new SquatCounter();
  const clock = new Clock(c, squatLandmarks);
  for (const angle of ramp(175, 110)) clock.frame(angle);
  c.finish(clock.t);
  assert.equal(c.count, 0);
  assert.equal(c.halfReps, 1);
});

test("squat form warning and statistics", () => {
  const c = new SquatCounter();
  const clock = new Clock(c, squatLandmarks);
  clock.rep(175, 80); // good rep
  clock.idle(175);
  clock.rep(175, 80, { lean: 400 }); // torso leans far forward (> 70 degrees)
  const s = c.summary();
  assert.equal(s.reps, 2);
  assert.equal(s.formIssueReps, 1);
  assert.equal(s.goodFormReps, 1);
  assert.ok(s.avgRepTime > 0.5 && s.avgRepTime < 3.0); // seconds, about 1.0 here
  assert.ok(s.bestDepth < 90);
});

test("push-ups count and ignore standing", () => {
  const c = new PushUpCounter();
  const clock = new Clock(c, pushupLandmarks);
  for (let i = 0; i < 3; i++) {
    clock.rep(175, 70);
    clock.idle(175);
  }
  assert.equal(c.count, 3);
  for (const angle of [...ramp(175, 50), ...ramp(50, 175)]) clock.frame(angle, { standing: true });
  assert.equal(c.count, 3);
});

test("push-up alignment warning", () => {
  const c = new PushUpCounter();
  new Clock(c, pushupLandmarks).rep(175, 70, { hipY: 200 }); // hips piked high
  const s = c.summary();
  assert.equal(s.reps, 1);
  assert.equal(s.formIssueReps, 1);
});

test("reset and restartMotion", () => {
  const c = new SquatCounter();
  new Clock(c, squatLandmarks).rep(175, 80);
  c.restartMotion();
  assert.equal(c.count, 1); // restart keeps the count and statistics
  c.reset();
  assert.equal(c.count, 0);
  assert.deepEqual(c.attempts, []);
});

test("missing person and hidden legs", () => {
  const c = new SquatCounter();
  assert.equal(c.update(null, 0).feedback, "No person detected");
  const hidden = Array.from({ length: 33 }, () => [0, 0, 0]);
  assert.match(c.update(hidden, 0.1).feedback, /Step back/);
});