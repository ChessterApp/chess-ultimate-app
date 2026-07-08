/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

function createMockEngine(name: string) {
  return {
    init: vi.fn().mockResolvedValue(undefined),
    sendUciCommands: vi.fn().mockImplementation((commands: string[]) => {
      if (commands.some((cmd) => cmd.startsWith('go depth'))) {
        return Promise.resolve(['bestmove e2e4 ponder d7d5'])
      }
      return Promise.resolve(['readyok'])
    }),
    shutdown: vi.fn(),
    crashed: false,
    constructor: { name },
  }
}

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

import {
  getStockfishEngine,
  getStockfishMove,
  subscribeStockfish,
  shutdownStockfish,
  warmStockfish,
  __resetStockfishForTests,
} from '../stockfishSingleton'

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
  __resetStockfishForTests()
  resetMockEngine(mockSF17Point, 'Stockfish17Point')
  resetMockEngine(mockSF16, 'Stockfish16')
  resetMockEngine(mockSF11, 'Stockfish11')
  sf17PointIsSupported.mockReturnValue(true)
  sf16IsSupported.mockReturnValue(true)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('stockfishSingleton init-once semantics', () => {
  it('returns the same promise for concurrent calls and inits once', async () => {
    const p1 = getStockfishEngine()
    const p2 = getStockfishEngine()
    expect(p1).toBe(p2)
    await p1
    expect(mockSF17Point.init).toHaveBeenCalledTimes(1)
  })

  it('reuses the resolved engine across sequential calls', async () => {
    const a = await getStockfishEngine()
    const b = await getStockfishEngine()
    expect(a).toBe(b)
    expect(mockSF17Point.init).toHaveBeenCalledTimes(1)
  })

  it('enables UCI_LimitStrength during init', async () => {
    await getStockfishEngine()
    const call = mockSF17Point.sendUciCommands.mock.calls.find((c: string[][]) =>
      c[0].some((cmd: string) => cmd.includes('UCI_LimitStrength value true')),
    )
    expect(call).toBeDefined()
  })

  it('warmStockfish kicks off init without a subscriber', async () => {
    warmStockfish()
    await getStockfishEngine()
    expect(mockSF17Point.init).toHaveBeenCalledTimes(1)
  })

  it('re-initializes after shutdown', async () => {
    await getStockfishEngine()
    expect(mockSF17Point.init).toHaveBeenCalledTimes(1)
    shutdownStockfish()
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
    await getStockfishEngine()
    expect(mockSF17Point.init).toHaveBeenCalledTimes(2)
  })
})

describe('stockfishSingleton getStockfishMove', () => {
  it('returns the parsed best move', async () => {
    await getStockfishEngine()
    const move = await getStockfishMove('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 2100)
    expect(move).toBe('e2e4')
  })

  it('only sends UCI_Elo when the target elo changes', async () => {
    await getStockfishEngine()
    mockSF17Point.sendUciCommands.mockClear()

    // 2100 is the initial elo — no elo command expected.
    await getStockfishMove('fen1', 2100)
    expect(
      mockSF17Point.sendUciCommands.mock.calls.find((c: string[][]) =>
        c[0].some((cmd: string) => cmd.includes('UCI_Elo value 2100')),
      ),
    ).toBeUndefined()

    // Changing elo should send the update.
    await getStockfishMove('fen2', 2600)
    expect(
      mockSF17Point.sendUciCommands.mock.calls.find((c: string[][]) =>
        c[0].some((cmd: string) => cmd.includes('UCI_Elo value 2600')),
      ),
    ).toBeDefined()
  })
})

describe('stockfishSingleton subscribe / idle timeout', () => {
  it('does not shut down while subscribers remain', async () => {
    vi.useFakeTimers()
    await getStockfishEngine()
    const unsub = subscribeStockfish()
    vi.advanceTimersByTime(60 * 60 * 1000)
    expect(mockSF17Point.shutdown).not.toHaveBeenCalled()
    unsub()
  })

  it('shuts down after the idle timeout once the last subscriber leaves', async () => {
    vi.useFakeTimers()
    await getStockfishEngine()
    const unsub = subscribeStockfish()
    unsub()

    vi.advanceTimersByTime(9 * 60 * 1000)
    expect(mockSF17Point.shutdown).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2 * 60 * 1000)
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })

  it('cancels the idle shutdown when a new subscriber arrives', async () => {
    vi.useFakeTimers()
    await getStockfishEngine()
    const unsub = subscribeStockfish()
    unsub()

    vi.advanceTimersByTime(5 * 60 * 1000)
    const unsub2 = subscribeStockfish()
    vi.advanceTimersByTime(10 * 60 * 1000)
    expect(mockSF17Point.shutdown).not.toHaveBeenCalled()
    unsub2()
  })

  it('waits for all subscribers before starting the idle timer', async () => {
    vi.useFakeTimers()
    await getStockfishEngine()
    const unsubA = subscribeStockfish()
    const unsubB = subscribeStockfish()

    unsubA()
    vi.advanceTimersByTime(30 * 60 * 1000)
    expect(mockSF17Point.shutdown).not.toHaveBeenCalled()

    unsubB()
    vi.advanceTimersByTime(11 * 60 * 1000)
    expect(mockSF17Point.shutdown).toHaveBeenCalled()
  })
})
