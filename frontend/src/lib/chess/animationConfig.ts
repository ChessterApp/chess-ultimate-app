/**
 * Unified animation speed control for chess pieces
 * Central source of truth for piece animation durations
 */

export const PIECE_ANIMATION_CONFIG = {
  INSTANT: 0,
  FAST: 100,
  NORMAL: 200,
  SLOW: 400,
} as const;

export type AnimationSpeed = keyof typeof PIECE_ANIMATION_CONFIG;

/**
 * Get animation duration in milliseconds for a given speed
 * @param speed - Animation speed setting (instant, fast, normal, slow)
 * @returns Duration in milliseconds
 */
export function getAnimationDuration(speed: AnimationSpeed): number {
  return PIECE_ANIMATION_CONFIG[speed];
}
