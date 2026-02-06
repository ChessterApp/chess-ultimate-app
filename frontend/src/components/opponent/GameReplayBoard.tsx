'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'
import { useTranslations } from 'next-intl'
import { useReplayStockfish } from '@/hooks/useReplayStockfish'
import ReplayEvalBar from './ReplayEvalBar'
import ReplayEngineLines from './ReplayEngineLines'

interface GameInfo {
  white_name: string
  black_name: string
  white_elo: number | null
  black_elo: number | null
  result: string
  date: string
  event: string
  eco: string
}

interface GameReplayBoardProps {
  pgn: string
  gameInfo: GameInfo
  playerName: string
  onClose: () => void
}

export default function GameReplayBoard({
  pgn,
  gameInfo,
  playerName,
  onClose
}: GameReplayBoardProps) {
  const t = useTranslations('opponent')
  const [currentMoveIndex, setCurrentMoveIndex] = useState(-1)
  const [isAutoPlaying, setIsAutoPlaying] = useState(false)
  const [isFlipped, setIsFlipped] = useState(false)

  // Stockfish analysis
  const { evaluation, isAnalyzing, depth, analyze, stopAnalysis } = useReplayStockfish()

  // Parse PGN and build position history
  const { positions, moves, game } = useMemo(() => {
    const chess = new Chess()
    const positionHistory: string[] = [chess.fen()] // Starting position
    const moveHistory: { san: string; color: 'w' | 'b' }[] = []

    try {
      chess.loadPgn(pgn)
      const history = chess.history({ verbose: true })

      // Reset and replay to build position history
      chess.reset()
      positionHistory[0] = chess.fen()

      for (const move of history) {
        chess.move(move.san)
        positionHistory.push(chess.fen())
        moveHistory.push({ san: move.san, color: move.color })
      }
    } catch (error) {
      console.error('Error parsing PGN:', error)
    }

    return {
      positions: positionHistory,
      moves: moveHistory,
      game: chess
    }
  }, [pgn])

  // Determine board orientation based on player color and manual flip
  const baseOrientation = useMemo(() => {
    const playerIsWhite = gameInfo.white_name.toLowerCase().includes(playerName.toLowerCase())
    return playerIsWhite ? 'white' : 'black'
  }, [gameInfo.white_name, playerName])

  // Apply manual flip to orientation
  const orientation = isFlipped
    ? (baseOrientation === 'white' ? 'black' : 'white')
    : baseOrientation

  // Toggle board flip
  const toggleFlip = useCallback(() => {
    setIsFlipped(prev => !prev)
  }, [])

  // Current position FEN
  const currentFen = positions[currentMoveIndex + 1] || positions[0]

  // Trigger Stockfish analysis when position changes
  useEffect(() => {
    if (currentFen) {
      analyze(currentFen)
    }
    return () => {
      // Stop analysis when component unmounts or position changes
    }
  }, [currentFen, analyze])

  // Navigation functions
  const goToStart = useCallback(() => {
    setCurrentMoveIndex(-1)
    setIsAutoPlaying(false)
  }, [])

  const goToEnd = useCallback(() => {
    setCurrentMoveIndex(moves.length - 1)
    setIsAutoPlaying(false)
  }, [moves.length])

  const goToPrevious = useCallback(() => {
    setCurrentMoveIndex(prev => Math.max(-1, prev - 1))
  }, [])

  const goToNext = useCallback(() => {
    setCurrentMoveIndex(prev => Math.min(moves.length - 1, prev + 1))
  }, [moves.length])

  const goToMove = useCallback((index: number) => {
    setCurrentMoveIndex(index)
    setIsAutoPlaying(false)
  }, [])

  const toggleAutoPlay = useCallback(() => {
    setIsAutoPlaying(prev => !prev)
  }, [])

  // Auto-play effect
  useEffect(() => {
    if (!isAutoPlaying) return
    if (currentMoveIndex >= moves.length - 1) {
      setIsAutoPlaying(false)
      return
    }

    const timer = setTimeout(() => {
      setCurrentMoveIndex(prev => prev + 1)
    }, 1000)

    return () => clearTimeout(timer)
  }, [isAutoPlaying, currentMoveIndex, moves.length])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        goToPrevious()
        setIsAutoPlaying(false)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        goToNext()
        setIsAutoPlaying(false)
      } else if (e.key === 'Home') {
        e.preventDefault()
        goToStart()
      } else if (e.key === 'End') {
        e.preventDefault()
        goToEnd()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [goToPrevious, goToNext, goToStart, goToEnd, onClose])

  // Format moves into pairs for display
  const movePairs = useMemo(() => {
    const pairs: { number: number; white?: string; black?: string; whiteIndex: number; blackIndex?: number }[] = []
    for (let i = 0; i < moves.length; i += 2) {
      pairs.push({
        number: Math.floor(i / 2) + 1,
        white: moves[i]?.san,
        black: moves[i + 1]?.san,
        whiteIndex: i,
        blackIndex: moves[i + 1] ? i + 1 : undefined
      })
    }
    return pairs
  }, [moves])

  // Result display
  const getResultDisplay = () => {
    if (gameInfo.result === '1-0') return { text: '1-0', label: 'White wins' }
    if (gameInfo.result === '0-1') return { text: '0-1', label: 'Black wins' }
    if (gameInfo.result === '1/2-1/2') return { text: '1/2', label: 'Draw' }
    return { text: '*', label: 'Ongoing' }
  }

  const result = getResultDisplay()

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden">
      {/* Header with game info */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h3 className="font-semibold text-gray-900 dark:text-white">
            {t('replay.title')}
          </h3>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {gameInfo.eco} - {gameInfo.event}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          title={t('replay.close')}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="p-4">
        {/* Player info bar */}
        <div className="flex items-center justify-between mb-4 text-sm">
          {/* Black player (top when orientation is white) */}
          <div className={`flex items-center gap-2 ${orientation === 'white' ? 'order-1' : 'order-3'}`}>
            <span className="w-4 h-4 bg-gray-800 rounded-sm border border-gray-600"></span>
            <span className="font-medium text-gray-900 dark:text-white">{gameInfo.black_name}</span>
            {gameInfo.black_elo && (
              <span className="text-gray-500 dark:text-gray-400">({gameInfo.black_elo})</span>
            )}
          </div>

          {/* Result in the middle */}
          <div className="order-2 px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">
            <span className="font-bold text-gray-900 dark:text-white">{result.text}</span>
          </div>

          {/* White player (bottom when orientation is white) */}
          <div className={`flex items-center gap-2 ${orientation === 'white' ? 'order-3' : 'order-1'}`}>
            <span className="w-4 h-4 bg-white rounded-sm border border-gray-300"></span>
            <span className="font-medium text-gray-900 dark:text-white">{gameInfo.white_name}</span>
            {gameInfo.white_elo && (
              <span className="text-gray-500 dark:text-gray-400">({gameInfo.white_elo})</span>
            )}
          </div>
        </div>

        {/* Chess board with eval bar and engine lines */}
        <div className="flex flex-col lg:flex-row justify-center gap-4 mb-4">
          {/* Eval Bar + Board + Controls column */}
          <div className="flex flex-col items-center">
            {/* Eval Bar + Board row */}
            <div className="flex gap-2">
              {/* Evaluation thermometer */}
              <ReplayEvalBar
                evaluation={evaluation?.lines?.[0] ? {
                  cp: evaluation.lines[0].cp,
                  mate: evaluation.lines[0].mate
                } : null}
                isAnalyzing={isAnalyzing}
                depth={depth}
                orientation={orientation}
                height={400}
              />

              {/* Chess board */}
              <div className="w-[400px] aspect-square">
                <Chessboard
                  position={currentFen}
                  boardOrientation={orientation}
                  arePiecesDraggable={false}
                  customBoardStyle={{
                    borderRadius: '4px',
                    boxShadow: '0 2px 10px rgba(0, 0, 0, 0.3)'
                  }}
                />
              </div>
            </div>

            {/* Navigation controls - centered under eval bar + board */}
            <div className="flex items-center justify-center gap-2 mt-4">
              <button
                onClick={goToStart}
                disabled={currentMoveIndex === -1}
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={t('replay.start')}
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 6h2v12H6V6zm3.5 6l8.5 6V6l-8.5 6z" />
                </svg>
              </button>
              <button
                onClick={goToPrevious}
                disabled={currentMoveIndex === -1}
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="Previous (←)"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" />
                </svg>
              </button>
              <button
                onClick={toggleAutoPlay}
                className={`p-2 rounded-lg transition-colors ${
                  isAutoPlaying
                    ? 'bg-orange-500 text-white hover:bg-orange-600'
                    : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
                title={t('replay.autoPlay')}
              >
                {isAutoPlaying ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                )}
              </button>
              <button
                onClick={goToNext}
                disabled={currentMoveIndex >= moves.length - 1}
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="Next (→)"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
                </svg>
              </button>
              <button
                onClick={goToEnd}
                disabled={currentMoveIndex >= moves.length - 1}
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={t('replay.end')}
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 18l8.5-6L6 6v12zm2 0V6l6.5 6L8 18zm8-12h2v12h-2V6z" />
                </svg>
              </button>

              {/* Flip button */}
              <button
                onClick={toggleFlip}
                className="p-2 ml-2 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title={t('replay.flip')}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                </svg>
              </button>
            </div>
          </div>

          {/* Engine lines - shown to the right on desktop, below on mobile */}
          <div className="lg:w-64">
            <ReplayEngineLines
              lines={evaluation?.lines || []}
              isAnalyzing={isAnalyzing}
              currentFen={currentFen}
              depth={depth}
            />
          </div>
        </div>

        {/* Move counter */}
        <div className="text-center text-sm text-gray-500 dark:text-gray-400 mb-3">
          {t('replay.move')} {currentMoveIndex + 1} / {moves.length}
        </div>

        {/* Move list */}
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 max-h-48 overflow-y-auto">
          <div className="flex flex-wrap gap-1 text-sm font-mono">
            {movePairs.map((pair) => (
              <div key={pair.number} className="flex items-center">
                <span className="text-gray-500 dark:text-gray-400 w-8">{pair.number}.</span>
                {pair.white && (
                  <button
                    onClick={() => goToMove(pair.whiteIndex)}
                    className={`px-1.5 py-0.5 rounded ${
                      currentMoveIndex === pair.whiteIndex
                        ? 'bg-orange-500 text-white'
                        : 'hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-900 dark:text-white'
                    }`}
                  >
                    {pair.white}
                  </button>
                )}
                {pair.black && (
                  <button
                    onClick={() => goToMove(pair.blackIndex!)}
                    className={`px-1.5 py-0.5 rounded ml-1 ${
                      currentMoveIndex === pair.blackIndex
                        ? 'bg-orange-500 text-white'
                        : 'hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-900 dark:text-white'
                    }`}
                  >
                    {pair.black}
                  </button>
                )}
              </div>
            ))}
            {moves.length === 0 && (
              <span className="text-gray-500 dark:text-gray-400 italic">No moves</span>
            )}
          </div>
        </div>

        {/* Game date */}
        <div className="mt-3 text-center text-xs text-gray-500 dark:text-gray-400">
          {gameInfo.date}
        </div>
      </div>
    </div>
  )
}
