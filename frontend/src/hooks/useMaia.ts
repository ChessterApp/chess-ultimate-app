'use client'

import { useState, useEffect, useRef } from 'react'
import Maia, { MaiaStatus } from '@/lib/maia/maia'
import {
  getMaiaInstance,
  getMaiaState,
  subscribeMaia,
} from '@/lib/engine/maiaSingleton'
import { fetchMaiaMoveFromServer } from '@/lib/maia/serverFallback'

interface UseMaiaResult {
  status: MaiaStatus
  progress: number
  error: string | null
  /** True when the last evaluation was served by the backend fallback (local model not ready). */
  usingServerFallback: boolean
  evaluatePosition: (
    fen: string,
    eloSelf: number,
    eloOppo: number,
  ) => Promise<{ policy: Record<string, number>; value: number } | null>
  downloadModel: () => Promise<void>
  maia: Maia | null
}

/**
 * Subscribes to the module-level Maia singleton so the ONNX InferenceSession
 * persists across navigation. The worker is not terminated on unmount; an idle
 * timeout in the singleton frees it after the last consumer leaves.
 */
export function useMaia(): UseMaiaResult {
  const [state, setState] = useState(() => getMaiaState())
  const [usingServerFallback, setUsingServerFallback] = useState(false)
  const maiaRef = useRef<Maia | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return

    maiaRef.current = getMaiaInstance()
    // Sync any state that changed before this subscriber attached.
    setState(getMaiaState())
    const unsubscribe = subscribeMaia(setState)

    return () => {
      unsubscribe()
    }
  }, [])

  // Once the local model is ready, we've hot-swapped away from the server.
  useEffect(() => {
    if (state.status === 'ready') setUsingServerFallback(false)
  }, [state.status])

  const evaluatePosition = async (
    fen: string,
    eloSelf: number,
    eloOppo: number,
  ) => {
    // Fast path: local model is ready — run inference in the browser.
    if (maiaRef.current && state.status === 'ready') {
      try {
        const result = await maiaRef.current.evaluateMaia3(fen, eloSelf, eloOppo)
        if (result) return result
      } catch (err) {
        console.error('Local Maia evaluation failed, falling back to server:', err)
      }
    }

    // Fallback: local model not ready (or errored) — ask the backend, which
    // runs the same model and returns the same { policy, value } shape.
    try {
      const result = await fetchMaiaMoveFromServer(fen, eloSelf, eloOppo)
      setUsingServerFallback(true)
      return result
    } catch (err) {
      console.error('Server Maia fallback failed:', err)
      return null
    }
  }

  const downloadModel = async () => {
    if (!maiaRef.current) {
      throw new Error('Maia not initialized')
    }
    await maiaRef.current.downloadModel()
  }

  return {
    status: state.status,
    progress: state.progress,
    error: state.error,
    usingServerFallback,
    evaluatePosition,
    downloadModel,
    maia: maiaRef.current,
  }
}
