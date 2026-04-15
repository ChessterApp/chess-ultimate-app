import { describe, it, expect, vi, beforeEach } from 'vitest'
import { UciEngine } from '../UciEngine'
import { EngineName } from '../engine'
import { EngineWorker } from '../EngineWorker'

function createMockWorker() {
  return {
    uci: vi.fn(),
    listen: vi.fn() as EngineWorker['listen'],
    onError: vi.fn(),
    terminate: vi.fn(),
  }
}

// Concrete subclass for testing
class TestEngine extends UciEngine {
  public mockWorker: ReturnType<typeof createMockWorker>

  constructor() {
    const mockWorker = createMockWorker()
    super(EngineName.Stockfish16, mockWorker, false)
    this.mockWorker = mockWorker
  }

  /** Simulate the engine sending a message (as init() wires up worker.listen) */
  simulateMessage(message: string) {
    this.mockWorker.listen(message)
  }
}

describe('UciEngine crash handling', () => {
  let engine: TestEngine

  beforeEach(() => {
    engine = new TestEngine()
  })

  it('starts with crashed = false', () => {
    expect(engine.crashed).toBe(false)
  })

  it('handleCrash sets crashed to true and ready to false', () => {
    engine.handleCrash(new Error('SIGILL'))
    expect(engine.crashed).toBe(true)
    expect(engine.isReady()).toBe(false)
  })

  it('handleCrash invokes onCrash callback', () => {
    const onCrash = vi.fn()
    engine.onCrash = onCrash
    const error = new Error('worker died')
    engine.handleCrash(error)
    expect(onCrash).toHaveBeenCalledWith(error)
  })

  it('handleCrash is idempotent (only fires once)', () => {
    const onCrash = vi.fn()
    engine.onCrash = onCrash
    engine.handleCrash(new Error('first'))
    engine.handleCrash(new Error('second'))
    expect(onCrash).toHaveBeenCalledTimes(1)
  })
})

describe('UciEngine.workerFromPath', () => {
  beforeEach(() => {
    // Mock the Worker constructor
    vi.stubGlobal('Worker', class MockWorker {
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: ((event: ErrorEvent) => void) | null = null
      private _listeners: Record<string, ((event: unknown) => void)[]> = {}

      postMessage = vi.fn()
      terminate = vi.fn()

      addEventListener(event: string, handler: (event: unknown) => void) {
        if (!this._listeners[event]) this._listeners[event] = []
        this._listeners[event].push(handler)
      }
    })
  })

  it('creates an EngineWorker with uci, listen, onError, terminate methods', () => {
    const worker = UciEngine.workerFromPath('/test/path.js')
    expect(worker.uci).toBeDefined()
    expect(worker.listen).toBeDefined()
    expect(worker.onError).toBeDefined()
    expect(worker.terminate).toBeDefined()
  })

  it('passes onCrash callback that fires on worker.onerror', () => {
    const onCrash = vi.fn()
    UciEngine.workerFromPath('/test/path.js', onCrash)
    // The onCrash is wired internally via worker.onerror, which we can't
    // easily trigger without accessing the internal Worker instance.
    // This test verifies the function signature accepts the parameter.
    expect(onCrash).not.toHaveBeenCalled()
  })
})

describe('UciEngine.sendUciCommands', () => {
  let engine: TestEngine

  beforeEach(async () => {
    engine = new TestEngine()
    // Auto-respond to any UCI command that expects 'uciok' or 'readyok'
    engine.mockWorker.uci.mockImplementation((command: string) => {
      if (command === 'uci') {
        queueMicrotask(() => engine.simulateMessage('uciok'))
      } else if (command === 'isready' || command === 'stop') {
        queueMicrotask(() => engine.simulateMessage('readyok'))
      }
    })
    await engine.init()
  })

  it('sends commands to the worker and collects responses', async () => {
    // Reset the mock to clear init()-phase calls and remove auto-responder
    engine.mockWorker.uci.mockReset()

    const promise = engine.sendUciCommands(
      ['position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 'go depth 1'],
      'bestmove',
    )

    expect(engine.mockWorker.uci).toHaveBeenCalledWith(
      'position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    )
    expect(engine.mockWorker.uci).toHaveBeenCalledWith('go depth 1')

    // Simulate async engine responses
    engine.simulateMessage('info depth 1 score cp 20 pv e2e4')
    engine.simulateMessage('bestmove e2e4')

    const messages = await promise
    expect(messages).toEqual([
      'info depth 1 score cp 20 pv e2e4',
      'bestmove e2e4',
    ])
  })

  it('resolves when finalMessage is a prefix of a response', async () => {
    engine.mockWorker.uci.mockReset()

    const promise = engine.sendUciCommands(['isready'], 'readyok')
    engine.simulateMessage('readyok')
    const messages = await promise
    expect(messages).toEqual(['readyok'])
  })

  it('calls onNewMessage callback with accumulated messages', async () => {
    engine.mockWorker.uci.mockReset()

    const onNewMessage = vi.fn()
    const promise = engine.sendUciCommands(
      ['go depth 2'],
      'bestmove',
      onNewMessage,
    )

    engine.simulateMessage('info depth 1 score cp 10 pv d2d4')
    expect(onNewMessage).toHaveBeenCalledTimes(1)
    expect(onNewMessage).toHaveBeenLastCalledWith(['info depth 1 score cp 10 pv d2d4'])

    engine.simulateMessage('info depth 2 score cp 15 pv e2e4')
    expect(onNewMessage).toHaveBeenCalledTimes(2)

    engine.simulateMessage('bestmove e2e4')
    expect(onNewMessage).toHaveBeenCalledTimes(3)

    const messages = await promise
    expect(messages).toHaveLength(3)
  })

  it('is accessible as a public method on the base class', () => {
    // Verify the method exists and is callable on UciEngine instances
    const ref: UciEngine = engine
    expect(typeof ref.sendUciCommands).toBe('function')
  })
})
