/** Skeleton drawing on a <canvas>. Landmarks are [x, y, visibility] in pixel coordinates. */

// Landmark index pairs forming the skeleton (body only, no face details).
export const POSE_CONNECTIONS = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
  [27, 29], [29, 31], [27, 31], [28, 30], [30, 32], [28, 32],
];
export const BODY_POINTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];

const VISIBLE = 0.4;

export function drawSkeleton(ctx, landmarks, width, height) {
  ctx.clearRect(0, 0, width, height);
  if (!landmarks) return;

  const lineWidth = Math.max(3, width / 220);
  ctx.lineCap = "round";
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = "#00c8ff";
  for (const [a, b] of POSE_CONNECTIONS) {
    if (landmarks[a][2] > VISIBLE && landmarks[b][2] > VISIBLE) {
      ctx.beginPath();
      ctx.moveTo(landmarks[a][0], landmarks[a][1]);
      ctx.lineTo(landmarks[b][0], landmarks[b][1]);
      ctx.stroke();
    }
  }
  ctx.fillStyle = "#78ff8c";
  for (const i of BODY_POINTS) {
    if (landmarks[i][2] > VISIBLE) {
      ctx.beginPath();
      ctx.arc(landmarks[i][0], landmarks[i][1], lineWidth * 1.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}