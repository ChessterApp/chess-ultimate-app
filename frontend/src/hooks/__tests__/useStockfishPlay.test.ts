/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

// Shared mock engine factory
function createMockEngine(name: string) {
  return {
    init: vi.fn().mockResolvedValue(undefined),
    sendUciCommands: vi.fn().mockImplementation((commands: string[]) => {
      if (commands.some(cmd => cmd.startsWith('go depth'))) {
        return Promise.resolve(['bestmove e2e4 ponder d7d5'])
      }
      return Promise.resolve(['readyok'])
    }),
    shutdown: vi.fn(),
    crashed: false,
    constructor: { name },
  }
}

// vi.hoisted runs before vi.mock hoisting, making these available inside mock factories
const { mockSF17Point, mockSF16, mockSF11, sf17PointIsSupported, sf16IsSupported } = vi.hoisted(() => ({
  mockSF17Point: createMockEngine('Stockfish17Point'),
  mockSF16: createMockEngine('Stockfish16'),
  mockSF11: createMockEngine('Stockfish11'),
  sf17PointIsSupported: vi.fn().mockReturnValue(true),
  sf16IsSupported: vi.fn().mockReturnValue(true),
}))

vi.mock('@/stockfish/engine/Stockfish17Point', () => ({
  Stockfish17Point: Object.assign(
    vi.fn().mockImplementation(function () { return mockSF17Point }),
    { isSupported: sf17PointIsSupported },
  ),
}))

vi.mock('@/stockfish/engine/Stockfish16', () => ({
  Stockfish16: Object.assign(
    vi.fn().mockImplementation(function () { return mockSF16 }),
    { isSupported: sf16IsSupported },
  ),
}))

vi.mock('@/stockfish/engine/Stockfish11', () => ({
  Stockfish11: vi.fn().mockImplementation(function () { return mockSF11 }),
}))

import { useStockfishPlay } from '../useStockfishPlay'
import { __resetStockfishForTests } from '@/lib/engine/stockfishSingleton'

function resetMockEngine(engine: ReturnType<typeof createMockEngine>, name: string) {
  engine.init.mockReset().mockResolvedValue(undefined)
  engine.sendUciCommands.mockReset().mockImplementation((commands: string[]) => {
    if (commands.some((cmd: string) => cmd.startsWith('go depth'))) {
      return Promise.resolve(['bestmove e2e4 ponder d7d5'])
    }
    return Promise.resolve(['readyok'])
  })
  engine.shutdown.mockReset()
  engine.crashed = false
  engine.constructor = { name }
}

beforeEach(() => {
  vi.clearAllMocks()
  // The engine is a module-level singleton; reset it so each test re-inits.
  __resetStockfishForTests()
  resetMockEngine(mockSF17Point, 'Stockfish17Point')
  resetMockEngine(mockSF16, 'Stockfish16')
  resetMockEngine(mockSF11, 'Stockfish11')
  sf17PointIsSupported.mockReturnValue(true)
  sf16IsSupported.mockReturnValue(true)
})

describe('useStockfishPlay', () => {
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

  it('generates a move even before the hook observes ready (never waits on Maia)', async () => {
    const { result } = renderHook(() => useStockfishPlay())

    // Call getMove immediately, WITHOUT waiting for status === 'ready'.
    // getStockfishMove awaits engine init internally, so a Stockfish bot is
    // never blocked by the Maia model's readiness.
    expect(result.current.status).toBe('loading')
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

    await result.current.getMove(
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      2100
    )

    await result.current.getMove(
      'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      2600
    )

    // Verify UCI_Elo update was sent
    const eloCall = mockSF17Point.sendUciCommands.mock.calls.find(
      (call: string[][]) => call[0].some((cmd: string) => cmd.includes('UCI_Elo value 2600'))
    )
    expect(eloCall).toBeDefined()
  })
})

describe('useStockfishPlay fallback chain', () => {
  it('should prefer SF17.1 when supported', async () => {
    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish17Point')
    expect(mockSF17Point.init).toHaveBeenCalled()
    expect(mockSF16.init).not.toHaveBeenCalled()
    expect(mockSF11.init).not.toHaveBeenCalled()
  })

  it('should fall back to SF16 when SF17.1 is not supported', async () => {
    sf17PointIsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish16')
    expect(mockSF17Point.init).not.toHaveBeenCalled()
    expect(mockSF16.init).toHaveBeenCalled()
  })

  it('should fall back to SF16 when SF17.1 init throws', async () => {
    mockSF17Point.init.mockRejectedValue(new Error('WASM failed'))

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish16')
    expect(mockSF16.init).toHaveBeenCalled()
  })

  it('should fall back to SF16 when SF17.1 crashes during init', async () => {
    mockSF17Point.init.mockImplementation(async () => {
      mockSF17Point.crashed = true
    })

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish16')
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })

  it('should fall back to SF11 when SF17.1 and SF16 both unsupported', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    sf16IsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish11')
    expect(mockSF11.init).toHaveBeenCalled()
  })

  it('should fall back to SF11 when SF17.1 and SF16 init both throw', async () => {
    mockSF17Point.init.mockRejectedValue(new Error('SF17.1 failed'))
    mockSF16.init.mockRejectedValue(new Error('SF16 failed'))

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish11')
    expect(mockSF11.init).toHaveBeenCalled()
  })

  it('should set error status when all engines fail', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    sf16IsSupported.mockReturnValue(false)
    mockSF11.init.mockRejectedValue(new Error('SF11 failed'))

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('error')
    })

    expect(result.current.error).toBe('SF11 failed')
  })

  it('should fall back to SF11 when SF16 crashes after SF17.1 unsupported', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    mockSF16.init.mockImplementation(async () => {
      mockSF16.crashed = true
    })

    const { result } = renderHook(() => useStockfishPlay())

    await waitFor(() => {
      expect(result.current.status).toBe('ready')
    })

    expect(result.current.engineName).toBe('Stockfish11')
    expect(mockSF16.shutdown).toHaveBeenCalled()
  })
})
