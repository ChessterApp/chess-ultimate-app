'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { EngineName, LineEval, PositionEval } from '@/stockfish/engine/engine'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'
import { UciEngine } from '@/stockfish/engine/UciEngine'

interface UseReplayStockfishReturn {
  evaluation: PositionEval | null
  isAnalyzing: boolean
  depth: number
  analyze: (fen: string) => void
  stopAnalysis: () => void
}

const ANALYSIS_DEPTH = 18 // Moderate depth for fast response
const MULTI_PV = 3 // Top 3 lines
const DEBOUNCE_MS = 300 // Debounce rapid position changes

/**
 * Hook to manage Stockfish Web Worker for game replay analysis.
 * Uses Stockfish 16 (mobile-friendly, 6MB) for fast loading.
 */
export function useReplayStockfish(): UseReplayStockfishReturn {
  const [evaluation, setEvaluation] = useState<PositionEval | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [depth, setDepth] = useState(0)

  const engineRef = useRef<UciEngine | null>(null)
  const engineReadyRef = useRef(false)
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)
  const currentFenRef = useRef<string | null>(null)
  const mountedRef = useRef(true)

  // Initialize engine on mount
  useEffect(() => {
    mountedRef.current = true

    const initEngine = async () => {
      try {
        // Check if WebAssembly is supported
        if (typeof WebAssembly !== 'object') {
          console.warn('WebAssembly not supported, Stockfish analysis disabled')
          return
        }

        const engine = new Stockfish16()
        await engine.init()

        if (mountedRef.current) {
          engineRef.current = engine
          engineReadyRef.current = true
          console.log('Replay Stockfish engine initialized')
        } else {
          // Component unmounted during init, cleanup
          engine.shutdown()
        }
      } catch (error) {
        console.error('Failed to initialize Stockfish:', error)
      }
    }

    initEngine()

    return () => {
      mountedRef.current = false

      // Clear debounce timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }

      // Shutdown engine
      if (engineRef.current) {
        engineRef.current.shutdown()
        engineRef.current = null
        engineReadyRef.current = false
      }
    }
  }, [])

  // Update depth from evaluation
  useEffect(() => {
    if (evaluation?.lines?.[0]?.depth) {
      setDepth(evaluation.lines[0].depth)
    }
  }, [evaluation])

  const stopAnalysis = useCallback(() => {
    if (engineRef.current && engineReadyRef.current) {
      engineRef.current.stopSearch()
    }
    setIsAnalyzing(false)
  }, [])

  const analyze = useCallback((fen: string) => {
    // Clear any pending debounced analysis
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // Store the current FEN to track if it changes
    currentFenRef.current = fen

    // Debounce the analysis
    debounceTimerRef.current = setTimeout(async () => {
      if (!engineRef.current || !engineReadyRef.current) {
        console.warn('Engine not ready')
        return
      }

      // Check if FEN changed during debounce
      if (currentFenRef.current !== fen) {
        return
      }

      if (!mountedRef.current) return

      setIsAnalyzing(true)
      setDepth(0)

      try {
        const result = await engineRef.current.evaluatePositionWithUpdate({
          fen,
          depth: ANALYSIS_DEPTH,
          multiPv: MULTI_PV,
          setPartialEval: (partialEval) => {
            // Only update if this is still the current position
            if (mountedRef.current && currentFenRef.current === fen) {
              setEvaluation(partialEval)
              if (partialEval.lines?.[0]?.depth) {
                setDepth(partialEval.lines[0].depth)
              }
            }
          }
        })

        if (mountedRef.current && currentFenRef.current === fen) {
          setEvaluation(result)
          setIsAnalyzing(false)
        }
      } catch (error) {
        console.error('Analysis error:', error)
        if (mountedRef.current) {
          setIsAnalyzing(false)
        }
      }
    }, DEBOUNCE_MS)
  }, [])

  return {
    evaluation,
    isAnalyzing,
    depth,
    analyze,
    stopAnalysis
  }
}
