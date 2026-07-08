'use client'

import { useState, useEffect, useRef } from 'react'
import Maia, { MaiaStatus } from '@/lib/maia/maia'
import {
  getMaiaInstance,
  getMaiaState,
  subscribeMaia,
} from '@/lib/engine/maiaSingleton'

interface UseMaiaResult {
  status: MaiaStatus
  progress: number
  error: string | null
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

  const evaluatePosition = async (
    fen: string,
    eloSelf: number,
    eloOppo: number,
  ) => {
    if (!maiaRef.current) {
      console.error('Maia not initialized')
      return null
    }

    if (state.status !== 'ready') {
      console.error('Maia not ready, current status:', state.status)
      return null
    }

    try {
      const result = await maiaRef.current.evaluateMaia3(fen, eloSelf, eloOppo)
      return result
    } catch (err) {
      console.error('Evaluation error:', err)
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
    evaluatePosition,
    downloadModel,
    maia: maiaRef.current,
  }
}
