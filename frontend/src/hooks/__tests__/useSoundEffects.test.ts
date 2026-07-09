/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSoundEffects } from '../useSoundEffects'

// --- Mock HTMLAudioElement (the success sample) ---------------------------
let playBehavior: 'resolve' | 'reject' = 'resolve'
let audioInstances: MockAudio[] = []

class MockAudio {
  src: string
  preload = ''
  volume = 1
  currentTime = 0
  play = vi.fn(() =>
    playBehavior === 'resolve' ? Promise.resolve() : Promise.reject(new Error('play failed'))
  )
  addEventListener = vi.fn()
  constructor(src: string) {
    this.src = src
    audioInstances.push(this)
  }
}

// --- Mock AudioContext (the synth fallback) -------------------------------
let oscillatorCount = 0

function makeMockContext() {
  return {
    state: 'running',
    currentTime: 0,
    resume: vi.fn(),
    close: vi.fn(),
    destination: {},
    createOscillator: vi.fn(() => {
      oscillatorCount++
      return {
        type: 'sine',
        frequency: { setValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn(),
      }
    }),
    createGain: vi.fn(() => ({
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
    })),
  }
}

describe('useSoundEffects', () => {
  beforeEach(() => {
    playBehavior = 'resolve'
    audioInstances = []
    oscillatorCount = 0
    window.localStorage.clear()
    vi.stubGlobal('Audio', MockAudio as unknown as typeof Audio)
    ;(window as any).AudioContext = vi.fn(makeMockContext)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('plays the puzzle-solved sample for the success sound', () => {
    const { result } = renderHook(() => useSoundEffects())

    act(() => result.current.play('success'))

    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].src).toContain('/sounds/puzzle-solved.mp3')
    expect(audioInstances[0].play).toHaveBeenCalledTimes(1)
    // No synth oscillators when the sample plays fine.
    expect(oscillatorCount).toBe(0)
  })

  it('sets a non-jarring volume on the sample', () => {
    const { result } = renderHook(() => useSoundEffects())
    act(() => result.current.play('success'))
    expect(audioInstances[0].volume).toBe(0.5)
  })

  it('falls back to the synth chime when the sample fails to play', async () => {
    playBehavior = 'reject'
    const { result } = renderHook(() => useSoundEffects())

    await act(async () => {
      result.current.play('success')
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(audioInstances[0].play).toHaveBeenCalled()
    // Fallback success chime = two oscillator tones.
    expect(oscillatorCount).toBe(2)
  })

  it('does not play anything when sound is disabled', () => {
    window.localStorage.setItem('sound_enabled', JSON.stringify(false))
    const { result } = renderHook(() => useSoundEffects())

    act(() => result.current.play('success'))

    expect(audioInstances).toHaveLength(0)
    expect(oscillatorCount).toBe(0)
  })

  it('uses the synth (not the sample) for non-success sounds', () => {
    const { result } = renderHook(() => useSoundEffects())

    act(() => result.current.play('move'))

    expect(audioInstances).toHaveLength(0)
    expect(oscillatorCount).toBe(1)
  })
})
