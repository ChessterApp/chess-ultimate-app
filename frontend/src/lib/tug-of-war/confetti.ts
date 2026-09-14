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

// Handles for the sustained shower so it can be cancelled on rematch/unmount.
let showerTimer: ReturnType<typeof setInterval> | null = null;
let showerStop: ReturnType<typeof setTimeout> | null = null;

function stopShower(): void {
  if (showerTimer !== null) {
    clearInterval(showerTimer);
    showerTimer = null;
  }
  if (showerStop !== null) {
    clearTimeout(showerStop);
    showerStop = null;
  }
}

/**
 * Fire a ~1.8s celebration shower in the winning team's colours: repeated
 * bursts from centre + both bottom corners, so it reads as a real celebration
 * rather than a single pop. Cancelled cleanly by resetConfetti().
 */
export async function fireWinConfetti(winner: TeamSide): Promise<void> {
  if (typeof window === 'undefined') return;
  const confetti = (await import('canvas-confetti')).default;
  const colors = TEAM_COLORS[winner];

  stopShower();

  const burst = () => {
    confetti({ particleCount: 55, spread: 90, startVelocity: 45, origin: { x: 0.5, y: 0.6 }, colors });
    confetti({ particleCount: 35, angle: 60, spread: 70, origin: { x: 0, y: 1 }, colors });
    confetti({ particleCount: 35, angle: 120, spread: 70, origin: { x: 1, y: 1 }, colors });
  };

  burst();
  showerTimer = setInterval(burst, 250);
  showerStop = setTimeout(stopShower, 1800);
}

/** Immediately stop and clear the confetti canvas (used on rematch/unmount). */
export async function resetConfetti(): Promise<void> {
  stopShower();
  if (typeof window === 'undefined') return;
  const confetti = (await import('canvas-confetti')).default;
  confetti.reset();
}
