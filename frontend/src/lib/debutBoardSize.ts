/** Width of the Database eval bar. */
export const EVAL_BAR_WIDTH_PX = 16;

/** Width of the eval bar plus its gap, reserved beside the board when it shows. */
export const EVAL_BAR_RESERVE_PX = EVAL_BAR_WIDTH_PX + 4;

/**
 * Database-board size for a viewport width. `reservedPx` is room taken beside
 * the board (the eval bar); on phones the board shrinks so the row still fits
 * without horizontal scroll.
 */
export function debutBoardSize(windowWidth: number, reservedPx = 0): number {
  let size: number;
  if (windowWidth < 400) size = Math.min(windowWidth - 32, 320);
  else if (windowWidth < 600) size = Math.min(windowWidth - 24, 360);
  else if (windowWidth < 768) size = Math.min(windowWidth - 32, 420);
  else if (windowWidth < 1024) size = Math.min(windowWidth - 48, 480);
  else size = 520;
  return reservedPx > 0 ? Math.min(size, windowWidth - 24 - reservedPx) : size;
}

/**
 * Room kept left of the board for the eval bar, by viewport width only — never
 * by whether Stockfish is on — so toggling the engine never moves or resizes
 * the board. 0 when the bar fits in the board's natural side margin.
 */
export function evalBarGutter(windowWidth: number): number {
  const sideMargin = (windowWidth - debutBoardSize(windowWidth)) / 2;
  return sideMargin >= EVAL_BAR_RESERVE_PX ? 0 : EVAL_BAR_RESERVE_PX;
}
