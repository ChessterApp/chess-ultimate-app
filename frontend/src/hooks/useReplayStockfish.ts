'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { EngineName, PositionEval } from '@/stockfish/engine/engine'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'
import { Stockfish11 } from '@/stockfish/engine/Stockfish11'
import { UciEngine } from '@/stockfish/engine/UciEngine'

/** Friendly short name for the active engine variant. */
export type EngineVariant = 'sf16' | 'sf11' | null

interface UseReplayStockfishReturn {
  evaluation: PositionEval | null
  isAnalyzing: boolean
  isReady: boolean
  depth: number
  /** Non-null when all engines failed to init. */
  engineError: string | null
  /** Which engine is currently active, or null if none. */
  activeEngine: EngineName | null
  /** Friendly name for the active engine variant. */
  engineName: EngineVariant
  analyze: (fen: string) => void
  stopAnalysis: () => void
}

/** Map EngineName enum to friendly variant label. */
function toEngineVariant(name: EngineName | null): EngineVariant {
  if (name === EngineName.Stockfish16) return 'sf16'
  if (name === EngineName.Stockfish11) return 'sf11'
  return null
}

const ANALYSIS_DEPTH = 18 // Moderate depth for fast response
const MULTI_PV = 3 // Top 3 lines
const DEBOUNCE_MS = 300 // Debounce rapid position changes
const SF16_INIT_TIMEOUT_MS = 8_000

interface UseReplayStockfishOptions {
  enabled?: boolean
  /** Called when the engine fails — UI can auto-disable the toggle. */
  onError?: (message: string) => void
}

/**
 * Tries to create and init an engine within a timeout.
 * Returns the initialized engine or throws on failure/timeout.
 */
async function tryInitEngine(
  createEngine: () => UciEngine,
  timeoutMs: number,
  mountedRef: React.RefObject<boolean>,
  onCrash: () => void,
): Promise<UciEngine> {
  const engine = createEngine()
  engine.onCrash = onCrash

  const initPromise = engine.init()
  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Engine init timed out')), timeoutMs)
  )

  try {
    await Promise.race([initPromise, timeoutPromise])
  } catch (error) {
    // Clean up the failed engine
    try { engine.shutdown() } catch { /* already dead */ }
    throw error
  }

  if (!mountedRef.current) {
    engine.shutdown()
    throw new Error('Component unmounted during init')
  }

  return engine
}

/**
 * Hook to manage Stockfish Web Worker for game replay analysis.
 * Tries SF16 first (NNUE, 6MB). If it fails, crashes, or times out
 * within 8s, automatically falls back to SF11 (HCE).
 * Only initializes the WASM engine when enabled=true.
 */
export function useReplayStockfish(options: UseReplayStockfishOptions = {}): UseReplayStockfishReturn {
  const { enabled = false, onError } = options
  const [evaluation, setEvaluation] = useState<PositionEval | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isReady, setIsReady] = useState(false)
  const [depth, setDepth] = useState(0)
  const [engineError, setEngineError] = useState<string | null>(null)
  const [activeEngine, setActiveEngine] = useState<EngineName | null>(null)
  const [engineName, setEngineName] = useState<EngineVariant>(null)

  const engineRef = useRef<UciEngine | null>(null)
  const engineReadyRef = useRef(false)
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)
  const currentFenRef = useRef<string | null>(null)
  const mountedRef = useRef(true)

  const handleEngineFailure = useCallback((message: string) => {
    setEngineError(message)
    setIsReady(false)
    setIsAnalyzing(false)
    setActiveEngine(null)
    setEngineName(null)
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
        setActiveEngine(null)
        setEngineName(null)
      }
      return
    }

    // If we already recorded a fatal error, don't re-try in this mount
    if (engineError) return

    const initEngine = async () => {
      // Skip if already initialized
      if (engineRef.current) return

      if (typeof WebAssembly !== 'object') {
        handleEngineFailure('WebAssembly not supported')
        return
      }

      // Tier 1: Try SF16 (NNUE, requires SIMD)
      try {
        const engine = await tryInitEngine(
          () => new Stockfish16(),
          SF16_INIT_TIMEOUT_MS,
          mountedRef,
          () => {
            if (mountedRef.current) {
              handleEngineFailure('Chess engine crashed unexpectedly')
            }
          },
        )

        if (mountedRef.current) {
          engineRef.current = engine
          engineReadyRef.current = true
          setActiveEngine(EngineName.Stockfish16)
          setEngineName(toEngineVariant(EngineName.Stockfish16))
          setIsReady(true)
          return
        }
      } catch {
        // SF16 failed — fall through to SF11
        if (!mountedRef.current) return
      }

      // Tier 2: Fallback to SF11 (HCE, no SIMD needed)
      try {
        const engine = await tryInitEngine(
          () => new Stockfish11(),
          SF16_INIT_TIMEOUT_MS,
          mountedRef,
          () => {
            if (mountedRef.current) {
              handleEngineFailure('Chess engine crashed unexpectedly')
            }
          },
        )

        if (mountedRef.current) {
          engineRef.current = engine
          engineReadyRef.current = true
          setActiveEngine(EngineName.Stockfish11)
          setEngineName(toEngineVariant(EngineName.Stockfish11))
          setIsReady(true)
        }
      } catch {
        if (mountedRef.current) {
          handleEngineFailure('All engine versions failed to initialize')
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
        setActiveEngine(null)
        setEngineName(null)
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
    activeEngine,
    engineName,
    analyze,
    stopAnalysis
  }
}
