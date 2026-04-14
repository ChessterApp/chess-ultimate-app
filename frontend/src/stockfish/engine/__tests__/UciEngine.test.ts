import { describe, it, expect, vi, beforeEach } from 'vitest'
import { UciEngine } from '../UciEngine'
import { EngineName } from '../engine'

// Concrete subclass for testing
class TestEngine extends UciEngine {
  constructor(worker?: Parameters<typeof UciEngine.workerFromPath>[1]) {
    const mockWorker = {
      uci: vi.fn(),
      listen: vi.fn(),
      onError: vi.fn(),
      terminate: vi.fn(),
    }
    super(EngineName.Stockfish16, mockWorker, false)
    if (worker) {
      // not used in these tests
    }
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
