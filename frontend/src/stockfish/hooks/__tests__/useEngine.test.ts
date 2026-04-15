/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { EngineName } from '../../engine/engine'

function createMockEngine(name: string) {
  return {
    init: vi.fn().mockResolvedValue(undefined),
    sendUciCommands: vi.fn().mockResolvedValue(['readyok']),
    shutdown: vi.fn(),
    evaluatePositionWithUpdate: vi.fn(),
    crashed: false,
    constructor: { name },
  }
}

const {
  mockSF17Point, mockSF17, mockSF16, mockSF11,
  sf17PointIsSupported, sf17IsSupported, sf16IsSupported,
} = vi.hoisted(() => ({
  mockSF17Point: createMockEngine('Stockfish17Point'),
  mockSF17: createMockEngine('Stockfish17'),
  mockSF16: createMockEngine('Stockfish16'),
  mockSF11: createMockEngine('Stockfish11'),
  sf17PointIsSupported: vi.fn().mockReturnValue(true),
  sf17IsSupported: vi.fn().mockReturnValue(true),
  sf16IsSupported: vi.fn().mockReturnValue(true),
}))

vi.mock('../../engine/Stockfish17Point', () => ({
  Stockfish17Point: Object.assign(
    vi.fn().mockImplementation(function () { return mockSF17Point }),
    { isSupported: sf17PointIsSupported },
  ),
}))

vi.mock('../../engine/Stockfish17', () => ({
  Stockfish17: Object.assign(
    vi.fn().mockImplementation(function () { return mockSF17 }),
    { isSupported: sf17IsSupported },
  ),
}))

vi.mock('../../engine/Stockfish16', () => ({
  Stockfish16: Object.assign(
    vi.fn().mockImplementation(function () { return mockSF16 }),
    { isSupported: sf16IsSupported },
  ),
}))

vi.mock('../../engine/Stockfish11', () => ({
  Stockfish11: vi.fn().mockImplementation(function () { return mockSF11 }),
}))

import { useEngine } from '../useEngine'

function resetMockEngine(engine: ReturnType<typeof createMockEngine>, name: string) {
  engine.init.mockReset().mockResolvedValue(undefined)
  engine.sendUciCommands.mockReset().mockResolvedValue(['readyok'])
  engine.shutdown.mockReset()
  engine.crashed = false
  engine.constructor = { name }
}

beforeEach(() => {
  vi.clearAllMocks()
  resetMockEngine(mockSF17Point, 'Stockfish17Point')
  resetMockEngine(mockSF17, 'Stockfish17')
  resetMockEngine(mockSF16, 'Stockfish16')
  resetMockEngine(mockSF11, 'Stockfish11')
  sf17PointIsSupported.mockReturnValue(true)
  sf17IsSupported.mockReturnValue(true)
  sf16IsSupported.mockReturnValue(true)
})

describe('useEngine', () => {
  it('should return undefined initially', () => {
    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))
    expect(result.current).toBeUndefined()
  })

  it('should return undefined when disabled', async () => {
    const { result } = renderHook(() => useEngine(false, EngineName.Stockfish17Point))

    // Wait a tick to ensure no async init runs
    await new Promise((r) => setTimeout(r, 50))
    expect(result.current).toBeUndefined()
    expect(mockSF17Point.init).not.toHaveBeenCalled()
  })

  it('should return undefined when engineName is undefined', async () => {
    const { result } = renderHook(() => useEngine(true, undefined))

    await new Promise((r) => setTimeout(r, 50))
    expect(result.current).toBeUndefined()
  })

  it('should initialize the preferred engine when supported', async () => {
    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF17Point)
    })

    expect(mockSF17Point.init).toHaveBeenCalled()
    expect(mockSF17.init).not.toHaveBeenCalled()
    expect(mockSF16.init).not.toHaveBeenCalled()
    expect(mockSF11.init).not.toHaveBeenCalled()
  })

  it('should shutdown engine on unmount', async () => {
    const { result, unmount } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF17Point)
    })

    unmount()
    // setEngine updater callback is async — give React time to flush
    await new Promise((r) => setTimeout(r, 50))
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })
})

describe('useEngine fallback chain', () => {
  it('should fall back to SF17 when SF17.1 is not supported', async () => {
    sf17PointIsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF17)
    })

    expect(mockSF17Point.init).not.toHaveBeenCalled()
    expect(mockSF17.init).toHaveBeenCalled()
  })

  it('should fall back to SF17 when SF17.1 init throws', async () => {
    mockSF17Point.init.mockRejectedValue(new Error('WASM failed'))

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF17)
    })

    expect(mockSF17.init).toHaveBeenCalled()
  })

  it('should fall back to SF17 when SF17.1 crashes during init', async () => {
    mockSF17Point.init.mockImplementation(async () => {
      mockSF17Point.crashed = true
    })

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF17)
    })

    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })

  it('should fall back to SF16 when SF17.1 and SF17 both unsupported', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    sf17IsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF16)
    })

    expect(mockSF16.init).toHaveBeenCalled()
  })

  it('should fall back to SF11 when all SIMD engines unsupported', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    sf17IsSupported.mockReturnValue(false)
    sf16IsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF11)
    })

    expect(mockSF11.init).toHaveBeenCalled()
  })

  it('should fall back to SF11 when all higher engines init throw', async () => {
    mockSF17Point.init.mockRejectedValue(new Error('SF17.1 failed'))
    mockSF17.init.mockRejectedValue(new Error('SF17 failed'))
    mockSF16.init.mockRejectedValue(new Error('SF16 failed'))

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    await waitFor(() => {
      expect(result.current).toBe(mockSF11)
    })
  })

  it('should remain undefined when all engines fail', async () => {
    sf17PointIsSupported.mockReturnValue(false)
    sf17IsSupported.mockReturnValue(false)
    sf16IsSupported.mockReturnValue(false)
    mockSF11.init.mockRejectedValue(new Error('SF11 failed'))

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    // Wait for the fallback chain to exhaust
    await new Promise((r) => setTimeout(r, 100))
    expect(result.current).toBeUndefined()
  })

  it('should start fallback from the selected engine (SF16 selected)', async () => {
    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish16))

    await waitFor(() => {
      expect(result.current).toBe(mockSF16)
    })

    // Should NOT try engines above the selected one
    expect(mockSF17Point.init).not.toHaveBeenCalled()
    expect(mockSF17.init).not.toHaveBeenCalled()
    expect(mockSF16.init).toHaveBeenCalled()
  })

  it('should fallback from SF16 to SF11 when SF16 unsupported', async () => {
    sf16IsSupported.mockReturnValue(false)

    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish16))

    await waitFor(() => {
      expect(result.current).toBe(mockSF11)
    })

    expect(mockSF17Point.init).not.toHaveBeenCalled()
    expect(mockSF17.init).not.toHaveBeenCalled()
    expect(mockSF11.init).toHaveBeenCalled()
  })

  it('should directly use SF11 when SF11 is selected', async () => {
    const { result } = renderHook(() => useEngine(true, EngineName.Stockfish11))

    await waitFor(() => {
      expect(result.current).toBe(mockSF11)
    })

    expect(mockSF17Point.init).not.toHaveBeenCalled()
    expect(mockSF17.init).not.toHaveBeenCalled()
    expect(mockSF16.init).not.toHaveBeenCalled()
    expect(mockSF11.init).toHaveBeenCalled()
  })

  it('should shutdown cancelled engine on unmount during init', async () => {
    // Make init slow so unmount happens during it
    let resolveInit!: () => void
    mockSF17Point.init.mockImplementation(
      () => new Promise<void>((resolve) => { resolveInit = resolve })
    )

    const { unmount } = renderHook(() => useEngine(true, EngineName.Stockfish17Point))

    // Give effect time to start
    await new Promise((r) => setTimeout(r, 10))

    // Unmount before init completes
    unmount()

    // Now resolve init - the engine should be shutdown since component unmounted
    resolveInit()
    await new Promise((r) => setTimeout(r, 50))
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })
})
