'use client'

import { useState, useEffect, useRef } from 'react'
import { UciEngine } from '@/stockfish/engine/UciEngine'
import { Stockfish17Point } from '@/stockfish/engine/Stockfish17Point'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'
import { Stockfish11 } from '@/stockfish/engine/Stockfish11'

interface UseStockfishPlayResult {
  status: 'loading' | 'ready' | 'error'
  error: string | null
  engineName: string | null
  getMove: (fen: string, targetElo: number) => Promise<string | null>
}

/**
 * Attempts to initialize engines in order: SF17.1 → SF16 → SF11.
 * Returns the first engine that initializes successfully, or throws if all fail.
 */
async function initWithFallback(): Promise<UciEngine> {
  // Try SF17.1 first (best quality)
  if (Stockfish17Point.isSupported()) {
    try {
      const engine = new Stockfish17Point()
      await engine.init()
      if (!engine.crashed) return engine
      engine.shutdown()
    } catch (err) {
      console.warn('SF17.1 init failed, trying SF16:', err)
    }
  }

  // Try SF16 (good quality, smaller)
  if (Stockfish16.isSupported()) {
    try {
      const engine = new Stockfish16()
      await engine.init()
      if (!engine.crashed) return engine
      engine.shutdown()
    } catch (err) {
      console.warn('SF16 init failed, trying SF11:', err)
    }
  }

  // Fall back to SF11 (always works, no SIMD)
  const engine = new Stockfish11()
  await engine.init()
  return engine
}

export function useStockfishPlay(): UseStockfishPlayResult {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [engineName, setEngineName] = useState<string | null>(null)
  const engineRef = useRef<UciEngine | null>(null)
  const currentEloRef = useRef<number>(2100)

  useEffect(() => {
    if (typeof window === 'undefined') return
    let cancelled = false

    const initEngine = async () => {
      try {
        const engine = await initWithFallback()
        if (cancelled) {
          engine.shutdown()
          return
        }

        // Enable UCI_LimitStrength and set initial ELO
        await engine.sendUciCommands([
          'setoption name UCI_LimitStrength value true',
          `setoption name UCI_Elo value ${currentEloRef.current}`,
          'isready'
        ], 'readyok')

        engineRef.current = engine
        setEngineName(engine.constructor.name)
        setStatus('ready')
      } catch (err) {
        console.error('All Stockfish engines failed to initialize:', err)
        setError(err instanceof Error ? err.message : 'Failed to initialize Stockfish')
        setStatus('error')
      }
    }

    initEngine()

    return () => {
      cancelled = true
      if (engineRef.current) {
        engineRef.current.shutdown()
        engineRef.current = null
      }
    }
  }, [])

  const getMove = async (fen: string, targetElo: number): Promise<string | null> => {
    if (!engineRef.current) {
      console.error('Stockfish not initialized')
      return null
    }

    if (status !== 'ready') {
      console.error('Stockfish not ready, current status:', status)
      return null
    }

    try {
      // Update UCI_Elo if it changed
      if (targetElo !== currentEloRef.current) {
        await engineRef.current.sendUciCommands([
          `setoption name UCI_Elo value ${targetElo}`,
          'isready'
        ], 'readyok')
        currentEloRef.current = targetElo
      }

      // Get best move
      const messages = await engineRef.current.sendUciCommands([
        `position fen ${fen}`,
        'go depth 12'
      ], 'bestmove')

      // Parse bestmove from response
      const bestmoveLine = messages.find(msg => msg.startsWith('bestmove'))
      if (!bestmoveLine) {
        console.error('No bestmove found in response')
        return null
      }

      // Extract move from "bestmove e2e4" or "bestmove e2e4 ponder d7d5"
      const parts = bestmoveLine.split(' ')
      if (parts.length < 2) {
        console.error('Invalid bestmove format:', bestmoveLine)
        return null
      }

      return parts[1]
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
