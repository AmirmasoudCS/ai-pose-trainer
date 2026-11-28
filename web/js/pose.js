/**
 * Webcam frame -> body landmarks, using MediaPipe's PoseLandmarker (Tasks Vision for the web).
 * Runs entirely in the browser: video frames never leave the device.
 *
 * The library is loaded on demand (not at page load), so the page still opens and can show
 * a helpful message when the download fails, e.g. offline on the very first visit.
 * The library version is pinned: change VERSION below to upgrade.
 */
const VERSION = "0.10.21";
const LIBRARY_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}`;
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

export class PoseDetector {
  constructor(library, fileset) {
    this.library = library; // the loaded MediaPipe module
    this.fileset = fileset;
    this.landmarker = null;
    this.delegate = null; // "GPU" or "CPU"
    this._lastTimestamp = -1;
    this._switching = false;
  }

  /** Download and start the pose model (needs the internet the first time). */
  static async create() {
    const library = await import(`${LIBRARY_URL}/vision_bundle.mjs`);
    const fileset = await library.FilesetResolver.forVisionTasks(`${LIBRARY_URL}/wasm`);
    const detector = new PoseDetector(library, fileset);
    let lastError = null;
    for (const delegate of ["GPU", "CPU"]) {
      try {
        detector.landmarker = await detector._make(delegate);
        detector.delegate = delegate;
        return detector;
      } catch (error) {
        lastError = error; // GPU is not available everywhere: fall back to CPU
      }
    }
    throw lastError;
  }

  _make(delegate) {
    return this.library.PoseLandmarker.createFromOptions(this.fileset, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate },
      runningMode: "VIDEO",
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });
  }

  /**
   * Returns 33 [x, y, visibility] landmarks in pixel coordinates of the video, or null
   * when nobody is detected.
   */
  detect(video, nowMs) {
    if (!this.landmarker) return null;
    const timestamp = Math.max(Math.round(nowMs), this._lastTimestamp + 1); // must increase
    this._lastTimestamp = timestamp;

    let result;
    try {
      result = this.landmarker.detectForVideo(video, timestamp);
    } catch (error) {
      this._fallbackToCpu();
      return null;
    }
    const pose = result && result.landmarks && result.landmarks[0];
    if (!pose) return null;
    const w = video.videoWidth;
    const h = video.videoHeight;
    return pose.map((p) => [p.x * w, p.y * h, p.visibility ?? 1]);
  }

  /** Some phones fail on the GPU at the first frame: silently switch to the CPU. */
  _fallbackToCpu() {
    if (this.delegate !== "GPU" || this._switching) return;
    this._switching = true;
    this._make("CPU")
      .then((landmarker) => {
        this.landmarker = landmarker;
        this.delegate = "CPU";
      })
      .catch(() => {})
      .finally(() => {
        this._switching = false;
      });
  }
}