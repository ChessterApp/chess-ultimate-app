'use client'

import { useCallback, useRef, useEffect } from 'react'
import { useLocalStorage } from 'usehooks-ts'

type SoundType = 'move' | 'capture' | 'success' | 'error' | 'click' | 'navigate'

// All sounds generated programmatically via Web Audio API — no external files needed
const SOUND_CONFIGS: Record<SoundType, { frequency: number; duration: number; type: OscillatorType; volume: number; decay?: number; secondFreq?: number; delay?: number }> = {
  move: { frequency: 440, duration: 0.08, type: 'sine', volume: 0.15, decay: 0.06 },
  capture: { frequency: 300, duration: 0.12, type: 'triangle', volume: 0.2, decay: 0.1 },
  success: { frequency: 523, duration: 0.3, type: 'sine', volume: 0.15, secondFreq: 659, delay: 0.15 },
  error: { frequency: 200, duration: 0.25, type: 'sawtooth', volume: 0.1, decay: 0.2 },
  click: { frequency: 800, duration: 0.04, type: 'sine', volume: 0.08, decay: 0.03 },
  navigate: { frequency: 600, duration: 0.06, type: 'sine', volume: 0.08, decay: 0.05 },
}

export function useSoundEffects() {
  const [soundEnabled] = useLocalStorage<boolean>('sound_enabled', true)
  const [moveSound] = useLocalStorage<boolean>('sound_move', true)
  const ctxRef = useRef<AudioContext | null>(null)

  const getContext = useCallback(() => {
    if (!ctxRef.current || ctxRef.current.state === 'closed') {
      ctxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)()
    }
    if (ctxRef.current.state === 'suspended') {
      ctxRef.current.resume()
    }
    return ctxRef.current
  }, [])

  const playTone = useCallback((freq: number, duration: number, type: OscillatorType, volume: number, decay: number, startTime: number, ctx: AudioContext) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = type
    osc.frequency.setValueAtTime(freq, startTime)
    gain.gain.setValueAtTime(volume, startTime)
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(startTime)
    osc.stop(startTime + duration)
  }, [])

  const play = useCallback((sound: SoundType) => {
    if (!soundEnabled) return
    if ((sound === 'move' || sound === 'capture') && !moveSound) return

    try {
      const ctx = getContext()
      const config = SOUND_CONFIGS[sound]
      const now = ctx.currentTime

      playTone(config.frequency, config.duration, config.type, config.volume, config.decay || config.duration * 0.8, now, ctx)

      // Second tone for success chime
      if (config.secondFreq && config.delay) {
        playTone(config.secondFreq, config.duration, config.type, config.volume, config.decay || config.duration * 0.8, now + config.delay, ctx)
      }
    } catch {
      // Silently fail — sound is non-critical
    }
  }, [soundEnabled, moveSound, getContext, playTone])

  // Cleanup
  useEffect(() => {
    return () => {
      ctxRef.current?.close()
    }
  }, [])

  return { play }
}
