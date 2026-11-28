/**
 * Exercise logic: joint angles, state machines for rep counting, rule-based feedback
 * and per-repetition statistics. A direct port of pose_trainer/core/exercises.py, so
 * the web app and the desktop app count the same way.
 *
 * Educational demo only: the feedback is simple geometry, not a medical assessment.
 *
 * Landmarks are arrays [x, y, visibility] in PIXEL coordinates (33 of them, MediaPipe
 * order). Indices: shoulder 11/12, elbow 13/14, wrist 15/16, hip 23/24, knee 25/26,
 * ankle 27/28 (left/right).
 */

export const MIN_VISIBILITY = 0.5;

/** Angle in degrees at point b, formed by points a-b-c (each is [x, y, ...]). */
export function calculateAngle(a, b, c) {
  const radians =
    Math.atan2(c[1] - b[1], c[0] - b[0]) - Math.atan2(a[1] - b[1], a[0] - b[0]);
  const angle = Math.abs((radians * 180) / Math.PI);
  return angle > 180 ? 360 - angle : angle;
}

const mean = (values) =>
  values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : null;

/**
 * Shared rep-counting machinery.
 *
 * A full rep is counted when the main joint angle drops below DOWN_ANGLE and then rises
 * back above UP_ANGLE (hysteresis avoids double counts). A half rep is a clear attempt
 * (the angle dropped well below START_ANGLE) that returned to the top without reaching
 * DOWN_ANGLE; it is not counted and shows "Go lower". Tiny wobbles are ignored.
 *
 * All timestamps come from the `t` argument of update() (seconds), so the same code works
 * for the live camera and for recorded videos.
 */
export class Exercise {
  label = "Exercise";
  UP_ANGLE = 160;
  START_ANGLE = 150;
  DOWN_ANGLE = 100;
  HALF_REP_MARGIN = 15; // must go this far below START_ANGLE to count as a half rep
  SMOOTHING = 0.4; // 1.0 = no smoothing
  SIDES = []; // one array of landmark indices per body side
  VISIBLE = []; // positions inside those arrays that must be visible

  constructor() {
    this.count = 0;
    this.attempts = [];
    this._t = performance.now() / 1000;
    this.restartMotion();
  }

  /** Clear the repetition count, statistics and any movement in progress. */
  reset() {
    this.count = 0;
    this.attempts = [];
    this.restartMotion();
  }

  /** Forget the movement in progress but keep the count and statistics. */
  restartMotion() {
    this.stage = "up";
    this._angle = null;
    this._descending = false;
    this._sticky = null; // { message, ok, expiresAt }
    this._repStart = null;
    this._minAngle = null;
    this._issue = false;
  }

  update(_landmarks, _t) {
    throw new Error("not implemented");
  }

  get halfReps() {
    return this.attempts.filter((a) => !a.full).length;
  }

  /** Call when a session ends: a clear movement still in progress becomes a half rep. */
  finish(t) {
    if (t !== undefined && t !== null) this._t = t;
    if (
      this._descending &&
      this._minAngle !== null &&
      this._minAngle < this.START_ANGLE - this.HALF_REP_MARGIN
    ) {
      this._record(false);
    }
    this.restartMotion();
  }

  summary() {
    const full = this.attempts.filter((a) => a.full);
    const times = full.map((a) => a.duration);
    const depths = full.map((a) => a.minAngle);
    return {
      exercise: this.label,
      reps: full.length,
      halfReps: this.attempts.length - full.length,
      formIssueReps: full.filter((a) => a.formIssue).length,
      goodFormReps: full.filter((a) => !a.formIssue).length,
      avgRepTime: mean(times),
      fastestRep: times.length ? Math.min(...times) : null,
      slowestRep: times.length ? Math.max(...times) : null,
      avgDepth: mean(depths), // smaller angle = deeper
      bestDepth: depths.length ? Math.min(...depths) : null,
      downAngle: this.DOWN_ANGLE,
      attempts: this.attempts.map((a) => ({ ...a })),
    };
  }

  // ---- helpers for subclasses ------------------------------------------------
  _beginFrame(t) {
    this._t = t === undefined || t === null ? performance.now() / 1000 : t;
  }

  /** Use the body side the camera sees best; null if neither is visible. */
  _pickSide(lm) {
    let best = null;
    let bestVis = 0;
    for (const idx of this.SIDES) {
      const vis = Math.min(...this.VISIBLE.map((i) => lm[idx[i]][2]));
      if (vis > bestVis) {
        best = idx;
        bestVis = vis;
      }
    }
    return bestVis >= MIN_VISIBILITY ? best : null;
  }

  _smooth(raw) {
    this._angle =
      this._angle === null
        ? raw
        : this.SMOOTHING * raw + (1 - this.SMOOTHING) * this._angle;
    return this._angle;
  }

  _setSticky(message, ok, seconds = 1.5) {
    this._sticky = { message, ok, expiresAt: this._t + seconds };
  }

  _stickyFeedback() {
    return this._sticky && this._t < this._sticky.expiresAt ? this._sticky : null;
  }

  /** Remember that a form warning appeared during the current rep. */
  _flagIssue() {
    if (this._descending || this.stage === "down") this._issue = true;
  }

  _record(full) {
    this.attempts.push({
      start: this._repStart,
      end: this._t,
      duration: this._t - this._repStart,
      minAngle: this._minAngle,
      full,
      formIssue: this._issue,
    });
  }

  _trackReps(angle) {
    if (this.stage === "up") {
      if (angle < this.START_ANGLE) {
        if (!this._descending) {
          this._descending = true;
          this._repStart = this._t;
          this._minAngle = angle;
          this._issue = false;
        }
        this._minAngle = Math.min(this._minAngle, angle);
      }
      if (angle < this.DOWN_ANGLE) {
        this.stage = "down";
      } else if (this._descending && angle > this.UP_ANGLE) {
        this._descending = false;
        if (this._minAngle < this.START_ANGLE - this.HALF_REP_MARGIN) {
          this._record(false);
          this._setSticky("Go lower", false);
        }
      }
    } else {
      // stage === "down"
      this._minAngle = Math.min(this._minAngle, angle);
      if (angle > this.UP_ANGLE) {
        this.stage = "up";
        this._descending = false;
        this.count += 1;
        this._record(true);
        this._setSticky("Good rep!", true, 1.0);
      }
    }
  }

  _state(angle, feedback, feedbackOk) {
    return {
      count: this.count,
      stage: this.stage,
      angle,
      feedback,
      feedbackOk,
      halfReps: this.halfReps,
    };
  }
}

/** Counts squats from the knee angle (hip-knee-ankle), best seen from the side. */
export class SquatCounter extends Exercise {
  label = "Squat";
  UP_ANGLE = 160;
  START_ANGLE = 150;
  DOWN_ANGLE = 100;
  MAX_TORSO_LEAN = 70; // degrees from vertical
  SIDES = [
    [11, 23, 25, 27], // left: shoulder, hip, knee, ankle
    [12, 24, 26, 28], // right
  ];
  VISIBLE = [1, 2, 3];

  update(lm, t) {
    this._beginFrame(t);
    if (!lm) return this._state(null, "No person detected", false);
    const side = this._pickSide(lm);
    if (!side) return this._state(null, "Step back: show hips, knees and ankles", false);

    const [shoulder, hip, knee, ankle] = side.map((i) => lm[i]);
    const angle = this._smooth(calculateAngle(hip, knee, ankle));
    this._trackReps(angle);

    // Torso lean: angle of the hip->shoulder line from vertical
    const dx = shoulder[0] - hip[0];
    const dy = shoulder[1] - hip[1];
    const lean = (Math.atan2(Math.abs(dx), Math.abs(dy) + 1e-6) * 180) / Math.PI;
    const leanBad = (this._descending || this.stage === "down") && lean > this.MAX_TORSO_LEAN;
    if (leanBad) this._flagIssue();

    const sticky = this._stickyFeedback();
    let message;
    let ok;
    if (sticky) {
      ({ message, ok } = sticky);
    } else if (leanBad) {
      [message, ok] = ["Keep your chest up", false];
    } else if (this.stage === "down") {
      [message, ok] = ["Good depth - now stand up", true];
    } else if (this._descending) {
      [message, ok] = ["Keep going down", true];
    } else {
      [message, ok] = ["Ready - start squatting", true];
    }
    return this._state(angle, message, ok);
  }
}

/**
 * Counts push-ups from the elbow angle (shoulder-elbow-wrist), side view. Only counts
 * while the body is roughly horizontal, so standing up or walking around never adds
 * reps. Body alignment is checked with the shoulder-hip-ankle (or knee) angle.
 */
export class PushUpCounter extends Exercise {
  label = "Push-up";
  UP_ANGLE = 155;
  START_ANGLE = 140;
  DOWN_ANGLE = 95;
  MAX_TILT = 40; // max degrees from horizontal (shoulder->hip line)
  MIN_BODY_ANGLE = 150; // below this the body is bent at the hips
  SIDES = [
    [11, 13, 15, 23, 25, 27], // left: shoulder, elbow, wrist, hip, knee, ankle
    [12, 14, 16, 24, 26, 28], // right
  ];
  VISIBLE = [0, 1, 2, 3]; // shoulder, elbow, wrist, hip

  update(lm, t) {
    this._beginFrame(t);
    if (!lm) return this._state(null, "No person detected", false);
    const side = this._pickSide(lm);
    if (!side) return this._state(null, "Show your full body from the side", false);

    const [shoulder, elbow, wrist, hip, knee, ankle] = side.map((i) => lm[i]);

    // Must be in a push-up position (body roughly horizontal)
    const tilt =
      (Math.atan2(Math.abs(hip[1] - shoulder[1]), Math.abs(hip[0] - shoulder[0]) + 1e-6) * 180) /
      Math.PI;
    if (tilt > this.MAX_TILT) {
      this.restartMotion();
      return this._state(null, "Get into push-up position", false);
    }

    const angle = this._smooth(calculateAngle(shoulder, elbow, wrist));
    this._trackReps(angle);

    // Body alignment: shoulder-hip-ankle (fall back to knee)
    const lower =
      ankle[2] >= MIN_VISIBILITY ? ankle : knee[2] >= MIN_VISIBILITY ? knee : null;
    let aligned = true;
    if (lower) aligned = calculateAngle(shoulder, hip, lower) >= this.MIN_BODY_ANGLE;
    if (!aligned) this._flagIssue();

    const sticky = this._stickyFeedback();
    let message;
    let ok;
    if (sticky) {
      ({ message, ok } = sticky);
    } else if (!aligned) {
      [message, ok] = ["Keep your body aligned", false];
    } else if (this.stage === "down") {
      [message, ok] = ["Good depth - push up", true];
    } else if (this._descending) {
      [message, ok] = ["Keep going down", true];
    } else {
      [message, ok] = ["Good posture", true];
    }
    return this._state(angle, message, ok);
  }
}

/** Exercises available in the UI, in display order. */
export const EXERCISES = {
  Squat: SquatCounter,
  "Push-up": PushUpCounter,
};