'use client'

import { useState, useEffect, useRef } from 'react'
import Maia, { MaiaStatus } from '@/lib/maia/maia'

const MODEL_URL = '/maia3/maia3_simplified.onnx'
const MODEL_VERSION = '3.0.0'

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

export function useMaia(): UseMaiaResult {
  const [status, setStatus] = useState<MaiaStatus>('loading')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const maiaRef = useRef<Maia | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const maia = new Maia({
      model: MODEL_URL,
      modelVersion: MODEL_VERSION,
      setStatus,
      setProgress,
      setError,
    })

    maiaRef.current = maia

    return () => {
      // Cleanup if needed
      maiaRef.current = null
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

    if (status !== 'ready') {
      console.error('Maia not ready, current status:', status)
      return null
    }

    try {
      const result = await maiaRef.current.evaluateMaia3(fen, eloSelf, eloOppo)
      return result
    } catch (err) {
      console.error('Evaluation error:', err)
      setError(err instanceof Error ? err.message : 'Evaluation failed')
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
    status,
    progress,
    error,
    evaluatePosition,
    downloadModel,
    maia: maiaRef.current,
  }
}
