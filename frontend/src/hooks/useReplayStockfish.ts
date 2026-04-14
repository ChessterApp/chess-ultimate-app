'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { EngineName, PositionEval } from '@/stockfish/engine/engine'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'
import { UciEngine } from '@/stockfish/engine/UciEngine'

interface UseReplayStockfishReturn {
  evaluation: PositionEval | null
  isAnalyzing: boolean
  isReady: boolean
  depth: number
  /** Non-null when Stockfish failed to init or crashed at runtime. */
  engineError: string | null
  analyze: (fen: string) => void
  stopAnalysis: () => void
}

const ANALYSIS_DEPTH = 18 // Moderate depth for fast response
const MULTI_PV = 3 // Top 3 lines
const DEBOUNCE_MS = 300 // Debounce rapid position changes

interface UseReplayStockfishOptions {
  enabled?: boolean
  /** Called when the engine fails — UI can auto-disable the toggle. */
  onError?: (message: string) => void
}

/**
 * Hook to manage Stockfish Web Worker for game replay analysis.
 * Uses Stockfish 16 (mobile-friendly, 6MB) for fast loading.
 * Only initializes the WASM engine when enabled=true.
 */
export function useReplayStockfish(options: UseReplayStockfishOptions = {}): UseReplayStockfishReturn {
  const { enabled = false, onError } = options
  const [evaluation, setEvaluation] = useState<PositionEval | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isReady, setIsReady] = useState(false)
  const [depth, setDepth] = useState(0)
  const [engineError, setEngineError] = useState<string | null>(null)

  const engineRef = useRef<UciEngine | null>(null)
  const engineReadyRef = useRef(false)
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)
  const currentFenRef = useRef<string | null>(null)
  const mountedRef = useRef(true)

  const handleEngineFailure = useCallback((message: string) => {
    setEngineError(message)
    setIsReady(false)
    setIsAnalyzing(false)
    engineReadyRef.current = false
    if (engineRef.current) {
      try { engineRef.current.shutdown() } catch { /* already dead */ }
      engineRef.current = null
    }
    onError?.(message)
  }, [onError])

  // Initialize engine only when enabled
  useEffect(() => {
    mountedRef.current = true

    if (!enabled) {
      // Shutdown engine if it was running
      if (engineRef.current) {
        engineRef.current.shutdown()
        engineRef.current = null
        engineReadyRef.current = false
        setIsReady(false)
      }
      return
    }

    // If we already recorded a fatal error, don't re-try in this mount
    if (engineError) return

    const initEngine = async () => {
      // Skip if already initialized
      if (engineRef.current) return

      try {
        if (typeof WebAssembly !== 'object') {
          handleEngineFailure('WebAssembly not supported')
          return
        }

        if (!Stockfish16.isSupported()) {
          handleEngineFailure('SIMD not supported by this browser')
          return
        }

        // Runtime SIMD smoke test — catches SIGILL before loading the 7MB binary
        const simdOk = await Stockfish16.smokeTestSimd()
        if (!simdOk) {
          handleEngineFailure('SIMD instructions not supported by this device')
          return
        }

        const engine = new Stockfish16()

        // Wire up crash handler so runtime SIGILL during analysis is caught
        engine.onCrash = () => {
          if (mountedRef.current) {
            handleEngineFailure('Chess engine crashed unexpectedly')
          }
        }

        // Race engine init against a timeout — WASM crashes (SIGILL) can hang forever
        const initPromise = engine.init()
        const timeoutPromise = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('Stockfish init timed out')), 10000)
        )

        await Promise.race([initPromise, timeoutPromise])

        if (mountedRef.current) {
          engineRef.current = engine
          engineReadyRef.current = true
          setIsReady(true)
        } else {
          engine.shutdown()
        }
      } catch (error) {
        if (mountedRef.current) {
          const msg = error instanceof Error ? error.message : 'Engine init failed'
          handleEngineFailure(msg)
        }
      }
    }

    initEngine()

    return () => {
      mountedRef.current = false

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }

      if (engineRef.current) {
        engineRef.current.shutdown()
        engineRef.current = null
        engineReadyRef.current = false
        setIsReady(false)
      }
    }
  }, [enabled, engineError, handleEngineFailure])

  // Reset error when user disables and re-enables
  useEffect(() => {
    if (!enabled && engineError) {
      setEngineError(null)
    }
  }, [enabled, engineError])

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
    // Don't attempt analysis if engine has errored
    if (engineError) return

    // Clear any pending debounced analysis
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    // Store the current FEN to track if it changes
    currentFenRef.current = fen

    // Debounce the analysis
    debounceTimerRef.current = setTimeout(async () => {
      if (!engineRef.current || !engineReadyRef.current) {
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
        if (mountedRef.current) {
          setIsAnalyzing(false)
          // If the engine crashed, surface the error
          if (engineRef.current?.crashed) {
            handleEngineFailure('Chess engine crashed during analysis')
          }
        }
      }
    }, DEBOUNCE_MS)
  }, [engineError, handleEngineFailure])

  return {
    evaluation,
    isAnalyzing,
    isReady,
    depth,
    engineError,
    analyze,
    stopAnalysis
  }
}
