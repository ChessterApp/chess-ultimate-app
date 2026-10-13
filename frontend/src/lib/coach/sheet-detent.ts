/**
 * The coach's bottom sheet on phones and portrait tablets (< 1024px): three
 * detents over a full-bleed board.
 *
 * - peek: the latest coach line, chips and the composer; the board keeps the full width.
 * - half: the chat history; the board shrinks but stays whole above it.
 * - full: the composer is in use (keyboard open) — the board collapses to a
 *   pinned mini-board; tapping it returns to peek. The board never disappears.
 *
 * The page renders the detents with pure CSS (`detentCss`, container units of
 * the shell); a drag measures the shell once and snaps with `snapDetent`, both
 * from the same constants.
 */

export type Detent = 'peek' | 'half' | 'full';

const ORDER: Detent[] = ['peek', 'half', 'full'];

/** The context bar (without the top safe area). */
export const CONTEXT_BAR_PX = 48;
/** The move strip under the board. */
export const MOVE_STRIP_PX = 36;
/** The pinned board while the sheet is full. */
export const MINI_BOARD_PX = 120;
/** Peek never gets smaller than this (line + chips + composer). */
export const PEEK_MIN_PX = 232;
/** Half is this share of the shell's height. */
export const HALF_RATIO = 0.6;
/** A release faster than this (px/s) moves one detent in its direction. */
export const FLING_PX_PER_S = 500;

export interface ShellBox {
  /** Shell height and width, px. */
  height: number;
  width: number;
  /** The context bar's real height (with the safe area), px. */
  bar: number;
  /** What the stage shows besides the board (move strip, play rows), px. */
  stageChrome: number;
}

/** Each detent's sheet height in px for a shell — the JS twin of `detentCss`. */
export function detentHeights({ height, width, bar, stageChrome }: ShellBox): Record<Detent, number> {
  const full = Math.max(0, height - bar - MINI_BOARD_PX);
  const peek = Math.min(full, Math.max(PEEK_MIN_PX, height - bar - stageChrome - width));
  const half = Math.min(full, Math.max(peek, Math.round(height * HALF_RATIO)));
  return { peek, half, full };
}

/**
 * The sheet height of each detent as CSS, in the shell's container units.
 * `--coach-bar-h` is the context bar's height with the safe area.
 */
export function detentCss(stageChrome: number): Record<Detent, string> {
  const full = `calc(100cqh - var(--coach-bar-h) - ${MINI_BOARD_PX}px)`;
  const peek = `min(${full}, max(${PEEK_MIN_PX}px, calc(100cqh - var(--coach-bar-h) - ${stageChrome}px - 100cqw)))`;
  const half = `min(${full}, max(${peek}, ${HALF_RATIO * 100}cqh))`;
  return { peek, half, full };
}

/**
 * Where a released drag lands: a fling moves to the next detent in its
 * direction, a slow release to the nearest one. `velocityY` > 0 is downwards
 * (the sheet shrinking).
 */
export function snapDetent(heightPx: number, velocityY: number, heights: Record<Detent, number>): Detent {
  if (velocityY < -FLING_PX_PER_S) {
    return ORDER.find((d) => heights[d] > heightPx + 1) ?? 'full';
  }
  if (velocityY > FLING_PX_PER_S) {
    return [...ORDER].reverse().find((d) => heights[d] < heightPx - 1) ?? 'peek';
  }
  let best: Detent = 'peek';
  for (const d of ORDER) {
    if (Math.abs(heights[d] - heightPx) < Math.abs(heights[best] - heightPx)) best = d;
  }
  return best;
}

export type SheetAction =
  | { type: 'snap'; detent: Detent }
  /** The grabber: tap / ArrowUp / ArrowDown. */
  | { type: 'expand' }
  | { type: 'collapse' }
  | { type: 'toggle' }
  /** The composer got focus: the keyboard is coming, make room. */
  | { type: 'composer_focus' }
  /** The pinned mini-board was tapped: back to the board. */
  | { type: 'mini_board_tap' }
  /** A game / puzzle / viewed game started or ended: show the board. */
  | { type: 'mode_changed' };

export function sheetReducer(detent: Detent, action: SheetAction): Detent {
  const i = ORDER.indexOf(detent);
  switch (action.type) {
    case 'snap':
      return action.detent;
    case 'expand':
      return ORDER[Math.min(ORDER.length - 1, i + 1)];
    case 'collapse':
      return ORDER[Math.max(0, i - 1)];
    case 'toggle':
      return detent === 'peek' ? 'half' : 'peek';
    case 'composer_focus':
      return 'full';
    case 'mini_board_tap':
    case 'mode_changed':
      return 'peek';
  }
}
