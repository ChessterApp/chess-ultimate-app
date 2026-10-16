/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach } from 'vitest'
import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import ReplayEngineLines from '../ReplayEngineLines'

// Start position with the move counter at 12 so numbering reads "12.e4 c5 13.Nf3".
const FEN_12 = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 12'
const SICILIAN = ['e2e4', 'c7c5', 'g1f3', 'd7d6', 'd2d4', 'c5d4', 'f3d4', 'g8f6', 'b1c3', 'a7a6']
const LINES = [
  { pv: SICILIAN, cp: 35, depth: 18 },
  { pv: ['d2d4', 'd7d5'], cp: 20, depth: 18 },
  { pv: ['g1f3'], mate: -3, depth: 18 },
]

afterEach(cleanup)

describe('ReplayEngineLines', () => {
  it('has no "Engine Analysis" title or "Depth:" text', () => {
    render(<ReplayEngineLines lines={LINES} currentFen={FEN_12} maxLines={3} />)
    expect(screen.queryByText(/engine analysis/i)).toBeNull()
    expect(screen.queryByText(/depth/i)).toBeNull()
  })

  it('shows 4 numbered full moves (8 half-moves) on one row', () => {
    render(<ReplayEngineLines lines={LINES} currentFen={FEN_12} maxLines={1} />)
    const moves = screen.getByTestId('engine-line-moves')
    expect(moves.textContent).toBe('12.e4 c5 13.Nf3 d6 14.d4 cxd4 15.Nxd4 Nf6')
    expect(moves.textContent).not.toContain('…')
    expect(screen.getByText('+0.35')).toBeTruthy()
  })

  it('renders at most maxLines rows', () => {
    const { rerender } = render(<ReplayEngineLines lines={LINES} currentFen={FEN_12} maxLines={1} />)
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(1)
    rerender(<ReplayEngineLines lines={LINES} currentFen={FEN_12} maxLines={3} />)
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(3)
    expect(screen.getByText('-M3')).toBeTruthy()
  })

  it('shows exactly maxLines skeletons until the engine has a line', () => {
    const { rerender } = render(<ReplayEngineLines lines={[]} currentFen={FEN_12} maxLines={1} />)
    expect(screen.getAllByTestId('engine-line-skeleton')).toHaveLength(1)
    rerender(<ReplayEngineLines lines={[]} currentFen={FEN_12} maxLines={3} />)
    expect(screen.getAllByTestId('engine-line-skeleton')).toHaveLength(3)
    expect(screen.queryByTestId('engine-line-row')).toBeNull()
  })
})
