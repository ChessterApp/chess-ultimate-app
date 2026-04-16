/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useReplayStockfish } from '../useReplayStockfish'
import { EngineName } from '@/stockfish/engine/engine'

// Controls for each engine tier
let sf17PointInitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'
let sf17InitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'
let sf16InitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'
let sf11InitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'

const mockSf17PointInit = vi.fn()
const mockSf17Init = vi.fn()
const mockSf16Init = vi.fn()
const mockSf11Init = vi.fn()
const mockSf17PointShutdown = vi.fn()
const mockSf17Shutdown = vi.fn()
const mockSf16Shutdown = vi.fn()
const mockSf11Shutdown = vi.fn()

vi.mock('@/stockfish/engine/Stockfish17Point', () => {
  return {
    Stockfish17Point: class MockStockfish17Point {
      crashed = false
      onCrash?: (error: unknown) => void
      init = vi.fn(() => {
        mockSf17PointInit()
        if (sf17PointInitBehavior === 'resolve') return Promise.resolve()
        if (sf17PointInitBehavior === 'reject') return Promise.reject(new Error('SF17.1 SIGILL'))
        return new Promise(() => { /* hang forever */ })
      })
      shutdown = vi.fn(() => { mockSf17PointShutdown() })
      stopSearch = vi.fn()
      evaluatePositionWithUpdate = vi.fn().mockResolvedValue({
        lines: [{ pv: ['e2e4'], cp: 35, depth: 18, multiPv: 1, fen: '' }]
      })
    }
  }
})

vi.mock('@/stockfish/engine/Stockfish17', () => {
  return {
    Stockfish17: class MockStockfish17 {
      crashed = false
      onCrash?: (error: unknown) => void
      init = vi.fn(() => {
        mockSf17Init()
        if (sf17InitBehavior === 'resolve') return Promise.resolve()
        if (sf17InitBehavior === 'reject') return Promise.reject(new Error('SF17 SIGILL'))
        return new Promise(() => { /* hang forever */ })
      })
      shutdown = vi.fn(() => { mockSf17Shutdown() })
      stopSearch = vi.fn()
      evaluatePositionWithUpdate = vi.fn().mockResolvedValue({
        lines: [{ pv: ['e2e4'], cp: 32, depth: 18, multiPv: 1, fen: '' }]
      })
    }
  }
})

vi.mock('@/stockfish/engine/Stockfish16', () => {
  return {
    Stockfish16: class MockStockfish16 {
      crashed = false
      onCrash?: (error: unknown) => void
      init = vi.fn(() => {
        mockSf16Init()
        if (sf16InitBehavior === 'resolve') return Promise.resolve()
        if (sf16InitBehavior === 'reject') return Promise.reject(new Error('SF16 SIGILL'))
        return new Promise(() => { /* hang forever */ })
      })
      shutdown = vi.fn(() => { mockSf16Shutdown() })
      stopSearch = vi.fn()
      evaluatePositionWithUpdate = vi.fn().mockResolvedValue({
        lines: [{ pv: ['e2e4'], cp: 30, depth: 18, multiPv: 1, fen: '' }]
      })
    }
  }
})

vi.mock('@/stockfish/engine/Stockfish11', () => {
  return {
    Stockfish11: class MockStockfish11 {
      crashed = false
      onCrash?: (error: unknown) => void
      init = vi.fn(() => {
        mockSf11Init()
        if (sf11InitBehavior === 'resolve') return Promise.resolve()
        if (sf11InitBehavior === 'reject') return Promise.reject(new Error('SF11 failed'))
        return new Promise(() => { /* hang forever */ })
      })
      shutdown = vi.fn(() => { mockSf11Shutdown() })
      stopSearch = vi.fn()
      evaluatePositionWithUpdate = vi.fn().mockResolvedValue({
        lines: [{ pv: ['e2e4'], cp: 20, depth: 18, multiPv: 1, fen: '' }]
      })
    }
  }
})

describe('useReplayStockfish', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sf17PointInitBehavior = 'resolve'
    sf17InitBehavior = 'resolve'
    sf16InitBehavior = 'resolve'
    sf11InitBehavior = 'resolve'

    if (typeof globalThis.WebAssembly === 'undefined') {
      // @ts-expect-error - mocking global
      globalThis.WebAssembly = { validate: () => true }
    }
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with default idle state', () => {
    const { result } = renderHook(() => useReplayStockfish())
    expect(result.current.isReady).toBe(false)
    expect(result.current.isAnalyzing).toBe(false)
    expect(result.current.engineError).toBeNull()
    expect(result.current.evaluation).toBeNull()
    expect(result.current.activeEngine).toBeNull()
    expect(result.current.engineName).toBeNull()
  })

  it('initializes SF17.1 (first tier) when enabled', async () => {
    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.engineError).toBeNull()
    expect(result.current.activeEngine).toBe(EngineName.Stockfish17Point)
    expect(result.current.engineName).toBe('sf17.1')
    expect(mockSf17PointInit).toHaveBeenCalled()
    expect(mockSf17Init).not.toHaveBeenCalled()
    expect(mockSf16Init).not.toHaveBeenCalled()
    expect(mockSf11Init).not.toHaveBeenCalled()
  })

  it('falls back to SF11 when all higher tiers fail', async () => {
    sf17PointInitBehavior = 'reject'
    sf17InitBehavior = 'reject'
    sf16InitBehavior = 'reject'

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.engineError).toBeNull()
    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
    expect(mockSf17PointInit).toHaveBeenCalled()
    expect(mockSf17Init).toHaveBeenCalled()
    expect(mockSf16Init).toHaveBeenCalled()
    expect(mockSf11Init).toHaveBeenCalled()
    expect(mockSf17PointShutdown).toHaveBeenCalled()
    expect(mockSf17Shutdown).toHaveBeenCalled()
    expect(mockSf16Shutdown).toHaveBeenCalled()
  })

  it('falls back to SF11 when a tier init times out', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    // SF17.1 hangs (times out), all others reject except SF11
    sf17PointInitBehavior = 'hang'
    sf17InitBehavior = 'reject'
    sf16InitBehavior = 'reject'

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    // Advance past the 8s timeout for SF17.1
    await act(async () => {
      vi.advanceTimersByTime(8_100)
    })

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
    expect(mockSf17PointShutdown).toHaveBeenCalled()
  }, 15_000)

  it('reports error when all engine tiers fail', async () => {
    sf17PointInitBehavior = 'reject'
    sf17InitBehavior = 'reject'
    sf16InitBehavior = 'reject'
    sf11InitBehavior = 'reject'

    const onError = vi.fn()
    const { result } = renderHook(() => useReplayStockfish({ enabled: true, onError }))

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    expect(result.current.engineError).toBe('All engine versions failed to initialize')
    expect(result.current.isReady).toBe(false)
    expect(result.current.activeEngine).toBeNull()
    expect(result.current.engineName).toBeNull()
    expect(onError).toHaveBeenCalled()
  })

  it('shuts down engine when disabled', async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useReplayStockfish({ enabled }),
      { initialProps: { enabled: true } }
    )

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    rerender({ enabled: false })

    await waitFor(() => {
      expect(result.current.isReady).toBe(false)
      expect(result.current.activeEngine).toBeNull()
      expect(result.current.engineName).toBeNull()
    })
  })

  it('does not attempt analysis when engineError is set', async () => {
    sf17PointInitBehavior = 'reject'
    sf17InitBehavior = 'reject'
    sf16InitBehavior = 'reject'
    sf11InitBehavior = 'reject'

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    act(() => {
      result.current.analyze('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    })

    expect(result.current.evaluation).toBeNull()
  })

  it('resets error state when disabled and re-enabled', async () => {
    sf17PointInitBehavior = 'reject'
    sf17InitBehavior = 'reject'
    sf16InitBehavior = 'reject'
    sf11InitBehavior = 'reject'

    const { result, rerender } = renderHook(
      ({ enabled }) => useReplayStockfish({ enabled }),
      { initialProps: { enabled: true } }
    )

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    // Disable — should clear error
    rerender({ enabled: false })

    await waitFor(() => {
      expect(result.current.engineError).toBeNull()
    })

    // Fix SF11 so re-enable succeeds
    sf11InitBehavior = 'resolve'

    rerender({ enabled: true })

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    // Higher tiers still reject, so should fall back to SF11
    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
  })
})
