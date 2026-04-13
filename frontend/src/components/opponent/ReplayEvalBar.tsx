'use client'

import { useMemo } from 'react'

interface Evaluation {
  cp?: number      // centipawns
  mate?: number    // mate in N moves
}

interface ReplayEvalBarProps {
  evaluation: Evaluation | null
  isAnalyzing: boolean
  depth: number
  orientation?: 'white' | 'black'
  height?: number
}

/**
 * Tailwind-based evaluation thermometer for game replay.
 * Shows white advantage at bottom, black at top.
 */
export default function ReplayEvalBar({
  evaluation,
  isAnalyzing,
  depth,
  orientation = 'white',
  height = 400
}: ReplayEvalBarProps) {

  // Calculate the percentage for the white section (0-100)
  const evalPercentage = useMemo(() => {
    if (!evaluation) return 50

    if (evaluation.mate !== undefined) {
      // Mate for white = 100%, mate for black = 0%
      return evaluation.mate > 0 ? 100 : 0
    }

    if (evaluation.cp !== undefined) {
      // Sigmoid-like mapping: small advantages are visually amplified
      // +1.0 pawn ≈ 65%, +2.0 ≈ 75%, +5.0 ≈ 90%
      const evalInPawns = evaluation.cp / 100
      const mapped = (2 / Math.PI) * Math.atan(evalInPawns / 2)  // range -1..+1
      return 50 + mapped * 45  // range 5..95
    }

    return 50
  }, [evaluation])

  // Format the evaluation text
  const evalText = useMemo(() => {
    if (!evaluation) return '0.00'

    if (evaluation.mate !== undefined) {
      return `M${Math.abs(evaluation.mate)}`
    }

    if (evaluation.cp !== undefined) {
      const evalInPawns = evaluation.cp / 100
      return evalInPawns >= 0
        ? `+${evalInPawns.toFixed(2)}`
        : evalInPawns.toFixed(2)
    }

    return '0.00'
  }, [evaluation])

  // Determine text color based on position
  const textColorClass = evalPercentage > 70 || evalPercentage < 30
    ? 'text-white'
    : 'text-gray-900'

  // When board is flipped, flip the bar visually
  const whiteHeight = orientation === 'white' ? evalPercentage : 100 - evalPercentage

  return (
    <div
      className="relative w-8 rounded overflow-hidden border border-gray-300 dark:border-gray-600 bg-gray-900 flex-shrink-0"
      style={{ height }}
      title={`Eval: ${evalText}${depth > 0 ? ` | Depth: ${depth}` : ''}`}
    >
      {/* White section (bottom) */}
      <div
        className="absolute bottom-0 left-0 right-0 bg-white transition-all duration-300 ease-in-out"
        style={{ height: `${whiteHeight}%` }}
      />

      {/* Evaluation text - rotated 90 degrees */}
      <div
        className={`absolute left-1/2 -translate-x-1/2 z-10 ${textColorClass} transition-all duration-300`}
        style={{
          top: whiteHeight > 50 ? '8px' : 'auto',
          bottom: whiteHeight <= 50 ? '8px' : 'auto',
          transform: 'translateX(-50%) rotate(-90deg)',
          transformOrigin: 'center',
          minWidth: '50px',
          textAlign: 'center'
        }}
      >
        <span
          className="text-[10px] font-bold whitespace-nowrap"
          style={{
            textShadow: evalPercentage > 70 || evalPercentage < 30
              ? '1px 1px 2px rgba(0,0,0,0.7)'
              : 'none'
          }}
        >
          {evalText}
        </span>
      </div>

      {/* Loading spinner overlay */}
      {isAnalyzing && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/10">
          <div className="w-3 h-3 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Depth indicator */}
      {depth > 0 && !isAnalyzing && (
        <div className="absolute bottom-0.5 left-1/2 -translate-x-1/2 z-20">
          <span className="text-[8px] text-gray-400 font-mono">{depth}</span>
        </div>
      )}
    </div>
  )
}
