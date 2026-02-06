'use client'

import { useMemo } from 'react'
import { Chess } from 'chess.js'
import { useTranslations } from 'next-intl'

interface EngineLine {
  pv: string[]       // principal variation moves in UCI format
  cp?: number        // centipawns
  mate?: number      // mate in N
  depth: number
}

interface ReplayEngineLinesProps {
  lines: EngineLine[]
  isAnalyzing: boolean
  currentFen: string
  depth: number
}

/**
 * Display top engine lines with evaluations.
 * Shows up to 3 suggested moves with their principal variations.
 */
export default function ReplayEngineLines({
  lines,
  isAnalyzing,
  currentFen,
  depth
}: ReplayEngineLinesProps) {
  const t = useTranslations('opponent')

  // Convert UCI moves to SAN notation
  const formattedLines = useMemo(() => {
    return lines.map((line, index) => {
      const sanMoves: string[] = []

      try {
        const chess = new Chess(currentFen)
        const movesToShow = Math.min(line.pv.length, 5) // Show first 5 moves

        for (let i = 0; i < movesToShow; i++) {
          const uciMove = line.pv[i]
          if (!uciMove) break

          // Parse UCI move (e.g., "e2e4" or "e7e8q" for promotion)
          const from = uciMove.slice(0, 2)
          const to = uciMove.slice(2, 4)
          const promotion = uciMove.length > 4 ? uciMove[4] : undefined

          try {
            const move = chess.move({
              from,
              to,
              promotion
            })
            if (move) {
              sanMoves.push(move.san)
            }
          } catch {
            // Invalid move, stop parsing
            break
          }
        }
      } catch {
        // Invalid FEN, return empty
      }

      return {
        ...line,
        sanMoves,
        rank: index + 1
      }
    })
  }, [lines, currentFen])

  // Format evaluation for display
  const formatEval = (line: EngineLine): string => {
    if (line.mate !== undefined) {
      return line.mate > 0 ? `M${line.mate}` : `-M${Math.abs(line.mate)}`
    }
    if (line.cp !== undefined) {
      const evalInPawns = line.cp / 100
      return evalInPawns >= 0
        ? `+${evalInPawns.toFixed(2)}`
        : evalInPawns.toFixed(2)
    }
    return '0.00'
  }

  // Get eval color based on value
  const getEvalColor = (line: EngineLine): string => {
    if (line.mate !== undefined) {
      return line.mate > 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
    }
    if (line.cp !== undefined) {
      if (line.cp > 100) return 'text-green-600 dark:text-green-400'
      if (line.cp < -100) return 'text-red-600 dark:text-red-400'
    }
    return 'text-gray-600 dark:text-gray-400'
  }

  // Rank indicator colors
  const getRankColor = (rank: number): string => {
    switch (rank) {
      case 1: return 'bg-orange-500 text-white'
      case 2: return 'bg-gray-400 text-white'
      case 3: return 'bg-amber-700 text-white'
      default: return 'bg-gray-300 text-gray-700'
    }
  }

  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 min-w-[200px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {t('engine.title')}
        </h4>
        {depth > 0 && (
          <span className="text-xs text-gray-400 font-mono">
            {t('engine.depth')}: {depth}
          </span>
        )}
      </div>

      {/* Engine lines */}
      <div className="space-y-2">
        {isAnalyzing && formattedLines.length === 0 ? (
          // Loading skeleton
          <>
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-2 animate-pulse">
                <div className="w-5 h-5 rounded bg-gray-300 dark:bg-gray-700" />
                <div className="w-12 h-4 rounded bg-gray-300 dark:bg-gray-700" />
                <div className="flex-1 h-4 rounded bg-gray-200 dark:bg-gray-800" />
              </div>
            ))}
          </>
        ) : formattedLines.length > 0 ? (
          formattedLines.map((line) => (
            <div
              key={line.rank}
              className={`flex items-start gap-2 p-2 rounded ${
                line.rank === 1 ? 'bg-white dark:bg-gray-800' : ''
              }`}
            >
              {/* Rank indicator */}
              <span className={`w-5 h-5 flex items-center justify-center rounded text-xs font-bold flex-shrink-0 ${getRankColor(line.rank)}`}>
                {line.rank}
              </span>

              {/* Evaluation */}
              <span className={`w-14 text-sm font-mono font-semibold flex-shrink-0 ${getEvalColor(line)}`}>
                {formatEval(line)}
              </span>

              {/* Moves */}
              <div className="flex-1 text-sm text-gray-700 dark:text-gray-300 font-mono overflow-hidden">
                {line.sanMoves.length > 0 ? (
                  <span className="truncate block">
                    {line.sanMoves.map((move, i) => (
                      <span key={i}>
                        {i === 0 ? (
                          <span className="font-semibold text-gray-900 dark:text-white">{move}</span>
                        ) : (
                          <span className="text-gray-500 dark:text-gray-400"> {move}</span>
                        )}
                      </span>
                    ))}
                    {line.pv.length > 5 && (
                      <span className="text-gray-400">...</span>
                    )}
                  </span>
                ) : (
                  <span className="text-gray-400 italic">...</span>
                )}
              </div>
            </div>
          ))
        ) : (
          // No lines yet
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            {isAnalyzing ? t('engine.analyzing') : t('engine.waiting')}
          </div>
        )}
      </div>

      {/* Analyzing indicator */}
      {isAnalyzing && formattedLines.length > 0 && (
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
          {t('engine.analyzing')}
        </div>
      )}
    </div>
  )
}
