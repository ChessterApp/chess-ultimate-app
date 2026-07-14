/** Outcome of a finished bot game, from the human player's point of view. */
export type GameOutcome = 'playerWin' | 'botWin' | 'draw'

/**
 * Minimal slice of a chess.js `Chess` instance needed to classify a finished
 * position. Kept narrow so the mapping can be unit-tested without a full board.
 */
export interface FinishedPosition {
  isCheckmate(): boolean
  isDraw(): boolean
  /** Side to move ('w' | 'b'). */
  turn(): 'w' | 'b'
}

/**
 * Map a finished position to an outcome relative to `playerColor`.
 *
 * On checkmate the side *to move* has been mated, so the other side won; that
 * winner is compared to the player's color. Every draw type (stalemate,
 * repetition, insufficient material, 50-move) collapses to `'draw'`. Returns
 * `null` when the game is not actually over (neither mate nor draw).
 */
export function outcomeFromPosition(
  chess: FinishedPosition,
  playerColor: 'w' | 'b',
): GameOutcome | null {
  if (chess.isCheckmate()) {
    const winner = chess.turn() === 'w' ? 'b' : 'w'
    return winner === playerColor ? 'playerWin' : 'botWin'
  }
  if (chess.isDraw()) return 'draw'
  return null
}
