/**
 * Win confetti for Tug of War.
 *
 * Colours match the celebration GIF sides: Team A = red (win-red.gif, LEFT),
 * Team B = blue (win-blue.gif, RIGHT). Uses the default canvas-confetti canvas,
 * which is created on `document.body` on first fire and torn down when the
 * animation ends; `resetConfetti()` clears it immediately on rematch so no
 * stray canvas survives.
 */

import type { TeamSide } from './types';

const TEAM_COLORS: Record<TeamSide, string[]> = {
  A: ['#ef4444', '#f87171', '#fca5a5', '#ffffff'],
  B: ['#3b82f6', '#60a5fa', '#93c5fd', '#ffffff'],
};

/** Fire a celebratory burst in the winning team's colours from both corners. */
export async function fireWinConfetti(winner: TeamSide): Promise<void> {
  if (typeof window === 'undefined') return;
  const confetti = (await import('canvas-confetti')).default;
  const colors = TEAM_COLORS[winner];

  // Center cannon.
  confetti({ particleCount: 120, spread: 90, startVelocity: 45, origin: { x: 0.5, y: 0.6 }, colors });
  // Both bottom corners, angled inward.
  confetti({ particleCount: 80, angle: 60, spread: 70, origin: { x: 0, y: 1 }, colors });
  confetti({ particleCount: 80, angle: 120, spread: 70, origin: { x: 1, y: 1 }, colors });
}

/** Immediately stop and clear the confetti canvas (used on rematch/unmount). */
export async function resetConfetti(): Promise<void> {
  if (typeof window === 'undefined') return;
  const confetti = (await import('canvas-confetti')).default;
  confetti.reset();
}
