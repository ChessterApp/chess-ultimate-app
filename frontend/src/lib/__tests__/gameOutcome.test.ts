/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest'
import { Chess } from 'chess.js'
import { outcomeFromPosition } from '../gameOutcome'

// Fool's mate — white to move and checkmated (Black won).
const WHITE_MATED = 'rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3'
// Scholar's mate — black to move and checkmated (White won).
const BLACK_MATED = 'r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4'
// Classic stalemate — black to move, no legal move, not in check.
const STALEMATE = '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'

describe('outcomeFromPosition — checkmate', () => {
  it('player (white) wins when black is mated', () => {
    expect(outcomeFromPosition(new Chess(BLACK_MATED), 'w')).toBe('playerWin')
  })

  it('player (white) loses when white is mated', () => {
    expect(outcomeFromPosition(new Chess(WHITE_MATED), 'w')).toBe('botWin')
  })

  it('player (black) wins when white is mated', () => {
    expect(outcomeFromPosition(new Chess(WHITE_MATED), 'b')).toBe('playerWin')
  })

  it('player (black) loses when black is mated', () => {
    expect(outcomeFromPosition(new Chess(BLACK_MATED), 'b')).toBe('botWin')
  })
})

describe('outcomeFromPosition — draw', () => {
  it('is a draw for the white player on stalemate', () => {
    expect(outcomeFromPosition(new Chess(STALEMATE), 'w')).toBe('draw')
  })

  it('is a draw for the black player on stalemate', () => {
    expect(outcomeFromPosition(new Chess(STALEMATE), 'b')).toBe('draw')
  })
})

describe('outcomeFromPosition — not over', () => {
  it('returns null for the starting position', () => {
    expect(outcomeFromPosition(new Chess(), 'w')).toBeNull()
  })
})
