/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useReplayStockfish } from '../useReplayStockfish'
import { EngineName } from '@/stockfish/engine/engine'

// Controls for SF16
let sf16Supported = true
let sf16InitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'

// Controls for SF11
let sf11InitBehavior: 'resolve' | 'reject' | 'hang' = 'resolve'

const mockSf16Init = vi.fn()
const mockSf11Init = vi.fn()
const mockSf16Shutdown = vi.fn()
const mockSf11Shutdown = vi.fn()

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

      static isSupported() { return sf16Supported }
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
    sf16Supported = true
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

  it('initializes SF16 when enabled and supported', async () => {
    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.engineError).toBeNull()
    expect(result.current.activeEngine).toBe(EngineName.Stockfish16)
    expect(result.current.engineName).toBe('sf16')
    expect(mockSf16Init).toHaveBeenCalled()
    expect(mockSf11Init).not.toHaveBeenCalled()
  })

  it('falls back to SF11 when SF16 is not supported', async () => {
    sf16Supported = false

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.engineError).toBeNull()
    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
    expect(mockSf16Init).not.toHaveBeenCalled()
    expect(mockSf11Init).toHaveBeenCalled()
  })

  it('falls back to SF11 when SF16 init throws', async () => {
    sf16InitBehavior = 'reject'

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
    expect(mockSf16Init).toHaveBeenCalled()
    expect(mockSf11Init).toHaveBeenCalled()
    expect(mockSf16Shutdown).toHaveBeenCalled() // SF16 should be cleaned up
  })

  it('falls back to SF11 when SF16 init times out', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    sf16InitBehavior = 'hang'

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    // Advance past the 8s SF16 timeout
    await act(async () => {
      vi.advanceTimersByTime(8_100)
    })

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
    expect(mockSf16Shutdown).toHaveBeenCalled()
  }, 15_000)

  it('reports error when both SF16 and SF11 fail', async () => {
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

  it('reports error when SF16 unsupported and SF11 fails', async () => {
    sf16Supported = false
    sf11InitBehavior = 'reject'

    const onError = vi.fn()
    const { result } = renderHook(() => useReplayStockfish({ enabled: true, onError }))

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    expect(result.current.engineError).toBe('All engine versions failed to initialize')
    expect(result.current.isReady).toBe(false)
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

    // SF16 still rejects, so should fall back to SF11
    expect(result.current.activeEngine).toBe(EngineName.Stockfish11)
    expect(result.current.engineName).toBe('sf11')
  })
})
