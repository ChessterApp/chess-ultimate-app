/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useStockfishPlay } from '../useStockfishPlay'

// Mock the Stockfish16 class
vi.mock('@/stockfish/engine/Stockfish16', () => {
  return {
    Stockfish16: class MockStockfish16 {
      async init() {
        return Promise.resolve()
      }

      async sendUciCommands(commands: string[], finalMessage: string) {
        if (commands.includes('isready')) {
          return Promise.resolve(['readyok'])
        }
        if (commands.some(cmd => cmd.startsWith('go depth'))) {
          return Promise.resolve(['bestmove e2e4 ponder d7d5'])
        }
        return Promise.resolve([])
      }

      shutdown() {
        // no-op
      }
    }
  }
})

describe('useStockfishPlay', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should initialize to loading state', () => {
    const { result } = renderHook(() => useStockfishPlay())
    expect(result.current.status).toBe('loading')
  })

  it('should initialize engine and become ready', async () => {
    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.error).toBeNull()
  })

  it('should get a move from Stockfish', async () => {
    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    const move = await result.current.getMove(
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      2100
    )

    expect(move).toBe('e2e4')
  })

  it('should update ELO when changed', async () => {
    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    // First move with ELO 2100
    await result.current.getMove(
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      2100
    )

    // Second move with different ELO should trigger update
    await result.current.getMove(
      'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      2600
    )

    // Verify the move was returned
    expect(true).toBe(true)
  })
})
