/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

interface MockMaiaOptions {
  setStatus: (status: string) => void
  setProgress: (progress: number) => void
  setError: (error: string) => void
}

const { mockMaiaInstances, MockMaia } = vi.hoisted(() => {
  const instances: Array<{ options: MockMaiaOptions; destroy: ReturnType<typeof vi.fn> }> = []
  class MockMaia {
    options: MockMaiaOptions
    destroy = vi.fn()
    downloadModel = vi.fn().mockResolvedValue(undefined)
    evaluateMaia3 = vi.fn()
    constructor(options: MockMaiaOptions) {
      this.options = options
      instances.push(this as unknown as { options: MockMaiaOptions; destroy: ReturnType<typeof vi.fn> })
    }
  }
  return { mockMaiaInstances: instances, MockMaia }
})

vi.mock('@/lib/maia/maia', () => ({ default: MockMaia }))

import {
  getMaiaInstance,
  getMaiaState,
  subscribeMaia,
  warmMaia,
  shutdownMaia,
  __resetMaiaForTests,
} from '../maiaSingleton'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('Worker', class MockWorker {})
  __resetMaiaForTests()
  mockMaiaInstances.length = 0
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('maiaSingleton init-once semantics', () => {
  it('creates the Maia instance at most once', () => {
    const a = getMaiaInstance()
    const b = getMaiaInstance()
    expect(a).toBe(b)
    expect(mockMaiaInstances.length).toBe(1)
  })

  it('warmMaia creates the instance', () => {
    warmMaia()
    expect(mockMaiaInstances.length).toBe(1)
  })

  it('starts in the loading state', () => {
    expect(getMaiaState().status).toBe('loading')
  })
})

describe('maiaSingleton subscribe / broadcast', () => {
  it('broadcasts status updates to subscribers and stores state', () => {
    const inst = getMaiaInstance()!
    const seen: string[] = []
    const unsub = subscribeMaia((s) => seen.push(s.status))

    ;(inst as unknown as { options: MockMaiaOptions }).options.setStatus('ready')

    expect(getMaiaState().status).toBe('ready')
    expect(seen).toContain('ready')
    unsub()
  })

  it('stops notifying after unsubscribe', () => {
    const inst = getMaiaInstance()!
    const seen: string[] = []
    const unsub = subscribeMaia((s) => seen.push(s.status))
    unsub()

    ;(inst as unknown as { options: MockMaiaOptions }).options.setStatus('ready')
    expect(seen).not.toContain('ready')
  })
})

describe('maiaSingleton idle timeout', () => {
  it('destroys Maia after the idle timeout and re-inits on demand', () => {
    vi.useFakeTimers()
    const inst = mockMaiaInstances[0] ?? (getMaiaInstance(), mockMaiaInstances[0])
    const unsub = subscribeMaia(() => {})
    unsub()

    vi.advanceTimersByTime(9 * 60 * 1000)
    expect(inst.destroy).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2 * 60 * 1000)
    expect(inst.destroy).toHaveBeenCalled()

    const inst2 = getMaiaInstance()
    expect(inst2).not.toBe(inst)
    expect(mockMaiaInstances.length).toBe(2)
  })

  it('cancels the idle shutdown when a new subscriber arrives', () => {
    vi.useFakeTimers()
    getMaiaInstance()
    const inst = mockMaiaInstances[0]
    const unsub = subscribeMaia(() => {})
    unsub()

    vi.advanceTimersByTime(5 * 60 * 1000)
    const unsub2 = subscribeMaia(() => {})
    vi.advanceTimersByTime(10 * 60 * 1000)
    expect(inst.destroy).not.toHaveBeenCalled()
    unsub2()
  })
})

describe('maiaSingleton shutdown', () => {
  it('destroys the instance and resets state to loading', () => {
    const inst = getMaiaInstance()!
    ;(inst as unknown as { options: MockMaiaOptions }).options.setStatus('ready')

    shutdownMaia()

    expect((inst as unknown as { destroy: ReturnType<typeof vi.fn> }).destroy).toHaveBeenCalled()
    expect(getMaiaState().status).toBe('loading')
  })
})
