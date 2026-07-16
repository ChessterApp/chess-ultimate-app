/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest'
import { liveOutcome, type LiveTerminal } from '../liveOutcome'

const WHITE = 'user-white'
const BLACK = 'user-black'

describe('liveOutcome mapping', () => {
  it('checkmate: winner sees playerWin, loser sees botWin (both POVs)', () => {
    const t: LiveTerminal = { winnerId: WHITE, result: '1-0', reason: 'checkmate' }
    expect(liveOutcome(t, WHITE)).toEqual({ outcome: 'playerWin', resigned: false })
    expect(liveOutcome(t, BLACK)).toEqual({ outcome: 'botWin', resigned: false })
  })

  it('flag win maps to the same win/loss vocabulary as checkmate', () => {
    const t: LiveTerminal = { winnerId: BLACK, result: '0-1', reason: 'flag' }
    expect(liveOutcome(t, BLACK)).toEqual({ outcome: 'playerWin', resigned: false })
    expect(liveOutcome(t, WHITE)).toEqual({ outcome: 'botWin', resigned: false })
  })

  it('resign: the resigning loser gets the resigned treatment, the winner does not', () => {
    // White resigned → Black wins.
    const t: LiveTerminal = { winnerId: BLACK, result: '0-1', reason: 'resign' }
    expect(liveOutcome(t, WHITE)).toEqual({ outcome: 'botWin', resigned: true })
    expect(liveOutcome(t, BLACK)).toEqual({ outcome: 'playerWin', resigned: false })
  })

  it('draw by agreement → draw for both, never resigned', () => {
    const t: LiveTerminal = { winnerId: null, result: '1/2-1/2', reason: 'draw' }
    expect(liveOutcome(t, WHITE)).toEqual({ outcome: 'draw', resigned: false })
    expect(liveOutcome(t, BLACK)).toEqual({ outcome: 'draw', resigned: false })
  })

  it.each(['stalemate', 'threefold', 'insufficient_material', 'fifty_move'])(
    'draw by %s → draw',
    (reason) => {
      const t: LiveTerminal = { winnerId: null, result: '1/2-1/2', reason }
      expect(liveOutcome(t, WHITE)).toEqual({ outcome: 'draw', resigned: false })
    },
  )

  it('abort → null (no modal), from either POV', () => {
    const t: LiveTerminal = { winnerId: null, result: null, reason: 'abort' }
    expect(liveOutcome(t, WHITE)).toBeNull()
    expect(liveOutcome(t, BLACK)).toBeNull()
  })

  it('expired → null (no modal)', () => {
    const t: LiveTerminal = { winnerId: null, result: null, reason: 'expired' }
    expect(liveOutcome(t, WHITE)).toBeNull()
  })

  it('a winner-less, non-draw end (unresolved) → null rather than a false loss', () => {
    const t: LiveTerminal = { winnerId: null, result: null, reason: null }
    expect(liveOutcome(t, WHITE)).toBeNull()
  })

  it('a spectator id (neither player) reads a decisive game as a loss', () => {
    const t: LiveTerminal = { winnerId: WHITE, result: '1-0', reason: 'checkmate' }
    expect(liveOutcome(t, 'someone-else')).toEqual({ outcome: 'botWin', resigned: false })
    expect(liveOutcome(t, null)).toEqual({ outcome: 'botWin', resigned: false })
  })
})
