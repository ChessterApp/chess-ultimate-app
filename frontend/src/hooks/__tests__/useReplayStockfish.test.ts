/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useReplayStockfish } from '../useReplayStockfish'

// Control whether smokeTestSimd succeeds
let smokeTestResult = true
// Control whether init resolves
let initShouldResolve = true

// Mock Stockfish16 class
vi.mock('@/stockfish/engine/Stockfish16', () => {
  return {
    Stockfish16: class MockStockfish16 {
      crashed = false
      onCrash?: (error: unknown) => void
      init = vi.fn(() => {
        if (initShouldResolve) return Promise.resolve()
        return new Promise(() => { /* never resolves */ })
      })
      shutdown = vi.fn()
      stopSearch = vi.fn()
      evaluatePositionWithUpdate = vi.fn().mockResolvedValue({
        lines: [{ pv: ['e2e4'], cp: 30, depth: 18, multiPv: 1, fen: '' }]
      })

      static isSupported() { return true }
      static async smokeTestSimd() { return smokeTestResult }
    }
  }
})

describe('useReplayStockfish', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    smokeTestResult = true
    initShouldResolve = true

    // Ensure WebAssembly is defined
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
  })

  it('initializes engine when enabled', async () => {
    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    expect(result.current.engineError).toBeNull()
  })

  it('shuts down engine when disabled', async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useReplayStockfish({ enabled }),
      { initialProps: { enabled: true } }
    )

    await waitFor(() => {
      expect(result.current.isReady).toBe(true)
    })

    // Disable
    rerender({ enabled: false })

    await waitFor(() => {
      expect(result.current.isReady).toBe(false)
    })
  })

  it('exposes engineError when SIMD smoke test fails', async () => {
    smokeTestResult = false
    const onError = vi.fn()

    const { result } = renderHook(() => useReplayStockfish({ enabled: true, onError }))

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    expect(result.current.engineError).toContain('SIMD')
    expect(onError).toHaveBeenCalled()
  })

  it('does not attempt analysis when engineError is set', async () => {
    smokeTestResult = false

    const { result } = renderHook(() => useReplayStockfish({ enabled: true }))

    await waitFor(() => {
      expect(result.current.engineError).not.toBeNull()
    })

    // analyze should be a no-op
    act(() => {
      result.current.analyze('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    })

    // Still no evaluation
    expect(result.current.evaluation).toBeNull()
  })
})
