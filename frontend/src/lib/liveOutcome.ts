import type { GameOutcome } from './gameOutcome'

/** Terminal facts from a finished live game, as `deriveTerminal` exposes them. */
export interface LiveTerminal {
  /** Clerk id of the winner, or null on a draw / non-result end. */
  winnerId: string | null
  /** '1-0' | '0-1' | '1/2-1/2' | null. */
  result: string | null
  /** 'checkmate' | 'resign' | 'flag' | 'draw' | 'stalemate' | 'abort' | … */
  reason: string | null
}

/** A live result mapped to the bot-game modal's vocabulary, viewer-relative. */
export interface LiveOutcome {
  outcome: GameOutcome
  /** True only when the viewer themselves resigned (a loss by resignation). */
  resigned: boolean
}

/** Ends that are not a chess result and therefore show no celebratory modal. */
const NO_MODAL_REASONS = new Set(['abort', 'expired'])

/**
 * Map a finished live game to a player-POV {@link GameOutcome} (+ resigned
 * flag) so the online end modal reuses the bot game's titles and animations.
 *
 * Returns `null` for aborted / expired games — an abandoned game is not a
 * result, so the page keeps its quiet banner instead of celebrating.
 */
export function liveOutcome(
  terminal: LiveTerminal,
  viewerId: string | null,
): LiveOutcome | null {
  const { winnerId, result, reason } = terminal
  if (reason && NO_MODAL_REASONS.has(reason)) return null
  if (result === '1/2-1/2' || reason === 'draw') {
    return { outcome: 'draw', resigned: false }
  }
  if (!winnerId) return null
  const iWon = winnerId === viewerId
  return {
    outcome: iWon ? 'playerWin' : 'botWin',
    resigned: !iWon && reason === 'resign',
  }
}
