// Pure geometry + spin math for the prize wheel. No DOM, no randomness — all
// deterministic so it can be unit-tested in isolation.
//
// Angle convention: degrees measured CLOCKWISE from the top (12 o'clock, where
// the pointer sits). This matches CSS `transform: rotate(Ndeg)`, which also
// rotates clockwise for positive N. Segment `i` (of `count`) occupies the
// angular range [i * seg, (i + 1) * seg) where seg = 360 / count.

export const DEG = Math.PI / 180;

/** Angular width of one segment, in degrees. */
export function segmentAngle(count: number): number {
  if (count <= 0) throw new Error('segmentAngle: count must be > 0');
  return 360 / count;
}

/** Angle (deg, clockwise from top) of the bisector of segment `index`. */
export function segmentCenterAngle(index: number, count: number): number {
  const seg = segmentAngle(count);
  return index * seg + seg / 2;
}

/**
 * Convert a polar angle (deg, clockwise from top) to an SVG (x, y) point on a
 * circle of radius `r` centered at (`cx`, `cy`). Top of the circle is angle 0.
 */
export function polarToCartesian(
  cx: number,
  cy: number,
  r: number,
  angleDeg: number,
): { x: number; y: number } {
  return {
    x: cx + r * Math.sin(angleDeg * DEG),
    y: cy - r * Math.cos(angleDeg * DEG),
  };
}

/**
 * SVG path `d` for a pie wedge from `startAngle` to `endAngle` (deg, clockwise
 * from top) on a circle of radius `r` centered at (`cx`, `cy`).
 */
export function wedgePath(
  cx: number,
  cy: number,
  r: number,
  startAngle: number,
  endAngle: number,
): string {
  const start = polarToCartesian(cx, cy, r, startAngle);
  const end = polarToCartesian(cx, cy, r, endAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  // sweep-flag 1 = clockwise, matching our angle convention.
  return [
    `M ${cx} ${cy}`,
    `L ${start.x} ${start.y}`,
    `A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`,
    'Z',
  ].join(' ');
}

const FULL_TURN = 360;

/**
 * Final wheel rotation (deg, clockwise) so segment `index` lands under the top
 * pointer, after `fullSpins` complete revolutions. Deterministic: the pointer
 * ends exactly on the segment's bisector.
 */
export function winnerRotation(
  index: number,
  count: number,
  fullSpins: number,
): number {
  const center = segmentCenterAngle(index, count);
  return fullSpins * FULL_TURN + (FULL_TURN - center);
}

/**
 * Inverse of {@link winnerRotation}: which segment index sits under the top
 * pointer given a final wheel `rotation` (deg, clockwise). Handles any rotation
 * magnitude and sign.
 */
export function pointerSegmentIndex(rotation: number, count: number): number {
  const seg = segmentAngle(count);
  // The pointer (top) maps to this angle in the wheel's own frame.
  const local = ((-rotation % FULL_TURN) + FULL_TURN) % FULL_TURN;
  return Math.floor(local / seg) % count;
}

/**
 * Auto-scaled label font size (px) so 6–30 segments all stay readable. Linearly
 * interpolates 20px (6 segments) → 9px (30 segments) and clamps outside that.
 */
export function segmentFontSize(count: number): number {
  const clamped = Math.min(30, Math.max(6, count));
  const size = 20 + ((clamped - 6) * (9 - 20)) / (30 - 6);
  return Math.round(size);
}
