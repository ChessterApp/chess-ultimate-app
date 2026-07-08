'use client'

import { useState, useEffect } from 'react'
import {
  getStockfishEngine,
  getStockfishMove,
  subscribeStockfish,
} from '@/lib/engine/stockfishSingleton'

interface UseStockfishPlayResult {
  status: 'loading' | 'ready' | 'error'
  error: string | null
  engineName: string | null
  getMove: (fen: string, targetElo: number) => Promise<string | null>
}

/**
 * Subscribes to the module-level Stockfish singleton so the engine persists
 * across navigation. The worker is not terminated on unmount; an idle timeout
 * in the singleton frees it after the last consumer leaves.
 */
export function useStockfishPlay(): UseStockfishPlayResult {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [engineName, setEngineName] = useState<string | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    let cancelled = false
    const unsubscribe = subscribeStockfish()

    getStockfishEngine()
      .then((engine) => {
        if (cancelled) return
        setEngineName(engine.constructor.name)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        console.error('All Stockfish engines failed to initialize:', err)
        setError(err instanceof Error ? err.message : 'Failed to initialize Stockfish')
        setStatus('error')
      })

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  const getMove = async (fen: string, targetElo: number): Promise<string | null> => {
    if (status !== 'ready') {
      console.error('Stockfish not ready, current status:', status)
      return null
    }

    try {
      return await getStockfishMove(fen, targetElo)
    } catch (err) {
      console.error('Stockfish getMove error:', err)
      setError(err instanceof Error ? err.message : 'Move generation failed')
      return null
    }
  }

  return {
    status,
    error,
    engineName,
    getMove,
  }
}
