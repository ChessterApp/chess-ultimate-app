/**
 * Board orientation for a Tug of War puzzle.
 *
 * The puzzle's `FEN` is the solver-to-move position (the opponent's setup move
 * is already applied), so the side-to-move in the FEN is the team that solves.
 * We always place that side on the bottom of the board.
 */
export function orientationFromFen(fen: string): 'white' | 'black' {
  return fen.split(' ')[1] === 'b' ? 'black' : 'white';
}
