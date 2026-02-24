'use client'

import { useCallback, useMemo } from 'react'

type HapticPattern = 'move' | 'capture' | 'check' | 'puzzleCorrect' | 'puzzleWrong' | 'buttonTap' | 'success' | 'error'

const PATTERNS: Record<HapticPattern, number | number[]> = {
  move: 10,
  capture: 25,
  check: [15, 30, 15],
  puzzleCorrect: [10, 20, 30],
  puzzleWrong: [50, 30, 50],
  buttonTap: 8,
  success: [10, 15, 25],
  error: [40, 20, 40],
}

export function useHaptic() {
  const isSupported = useMemo(() => {
    if (typeof window === 'undefined') return false
    return 'vibrate' in navigator
  }, [])

  const vibrate = useCallback((pattern: HapticPattern | number | number[]) => {
    if (!isSupported) return false
    try {
      const p = typeof pattern === 'string' ? PATTERNS[pattern] : pattern
      return navigator.vibrate(p)
    } catch {
      return false
    }
  }, [isSupported])

  const onMove = useCallback(() => vibrate('move'), [vibrate])
  const onCapture = useCallback(() => vibrate('capture'), [vibrate])
  const onCheck = useCallback(() => vibrate('check'), [vibrate])
  const onPuzzleCorrect = useCallback(() => vibrate('puzzleCorrect'), [vibrate])
  const onPuzzleWrong = useCallback(() => vibrate('puzzleWrong'), [vibrate])
  const onButtonTap = useCallback(() => vibrate('buttonTap'), [vibrate])
  const onSuccess = useCallback(() => vibrate('success'), [vibrate])
  const onError = useCallback(() => vibrate('error'), [vibrate])

  return {
    isSupported,
    vibrate,
    onMove,
    onCapture,
    onCheck,
    onPuzzleCorrect,
    onPuzzleWrong,
    onButtonTap,
    onSuccess,
    onError,
  }
}
