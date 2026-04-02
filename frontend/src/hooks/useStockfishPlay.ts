'use client'

import { useState, useEffect, useRef } from 'react'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'

interface UseStockfishPlayResult {
  status: 'loading' | 'ready' | 'error'
  error: string | null
  getMove: (fen: string, targetElo: number) => Promise<string | null>
}

export function useStockfishPlay(): UseStockfishPlayResult {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const engineRef = useRef<Stockfish16 | null>(null)
  const currentEloRef = useRef<number>(2100)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const initEngine = async () => {
      try {
        const engine = new Stockfish16()
        await engine.init()

        // Enable UCI_LimitStrength and set initial ELO
        await engine.sendUciCommands([
          'setoption name UCI_LimitStrength value true',
          `setoption name UCI_Elo value ${currentEloRef.current}`,
          'isready'
        ], 'readyok')

        engineRef.current = engine
        setStatus('ready')
      } catch (err) {
        console.error('Stockfish initialization error:', err)
        setError(err instanceof Error ? err.message : 'Failed to initialize Stockfish')
        setStatus('error')
      }
    }

    initEngine()

    return () => {
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
    getMove,
  }
}
