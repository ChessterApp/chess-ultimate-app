'use client'

import { useState, useEffect, useCallback } from 'react'
import { AnimatedChessBoard } from '@/components/chess'
import { ChevronLeft, ChevronRight, Check, Trophy, RotateCcw } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'

interface Puzzle {
  id: string
  order_index: number
  fen: string
  solution_move: string
  hint_text?: string
  completed: boolean
  attempts: number
}

interface PuzzleSequenceProps {
  courseSlug: string
  lessonSlug: string
  getToken: () => Promise<string | null>
  onAllPuzzlesComplete?: () => void
}

/**
 * PuzzleSequence - Lichess-style multi-puzzle component
 *
 * Features:
 * - Numbered puzzle buttons (1-12) instead of dots
 * - Lottie celebration animation on correct move
 * - Auto-advance to next puzzle after animation
 * - Info panel on the right with progress tracking
 */
export default function PuzzleSequence({
  courseSlug,
  lessonSlug,
  getToken,
  onAllPuzzlesComplete
}: PuzzleSequenceProps) {
  const t = useTranslations('puzzles')
  const tErrors = useTranslations('errors')
  const { showToast } = useToast()
  const [puzzles, setPuzzles] = useState<Puzzle[]>([])
  const [currentIndex, setCurrentIndex] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [completedCount, setCompletedCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [allComplete, setAllComplete] = useState(false)
  const [justSolved, setJustSolved] = useState(false)
  const [resetting, setResetting] = useState(false)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL

  // Fetch all puzzles for this lesson
  const fetchPuzzles = useCallback(async () => {
    try {
      const token = await getToken()
      if (!token) return

      const data = await apiFetch<any>(
        `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/puzzles`,
        {
          headers: { 'Authorization': `Bearer ${token}` }
        }
      )
      setPuzzles(data.puzzles || [])
      setTotalCount(data.total_count || 0)
      setCompletedCount(data.completed_count || 0)
      setCurrentIndex(data.current_index || 1)
      setAllComplete(data.completed_count >= data.total_count && data.total_count > 0)
    } catch (err) {
      console.error('Error fetching puzzles:', err)
      if (err instanceof ApiError) {
        if (err.status === 0) {
          showToast('Network error — check your connection', 'error')
        } else if (err.status === 408) {
          showToast('Request timed out — try again', 'error')
        }
      }
      setError(t('noPuzzles'))
    } finally {
      setLoading(false)
    }
  }, [apiUrl, courseSlug, lessonSlug, getToken])

  useEffect(() => {
    fetchPuzzles()
  }, [fetchPuzzles])

  // Mark current puzzle as complete and show Continue button
  const handlePuzzleComplete = async () => {
    try {
      const token = await getToken()
      if (!token) return

      let data: any
      try {
        data = await apiFetch<any>(
          `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/puzzles/${currentIndex}/complete`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ attempts: 1 })
          }
        )
      } catch (err) {
        console.error('Failed to mark puzzle complete')
        return
      }

      // Update local state
      setPuzzles(prev => prev.map(p =>
        p.order_index === currentIndex ? { ...p, completed: true } : p
      ))
      setCompletedCount(prev => prev + 1)
      setJustSolved(true)

      // Check if all puzzles are complete
      if (data.lesson_complete) {
        setAllComplete(true)
        onAllPuzzlesComplete?.()
      } else if (currentIndex < totalCount) {
        // Auto-advance to next puzzle after Lottie animation plays (1.5s + 300ms buffer)
        setTimeout(() => {
          setJustSolved(false)
          setCurrentIndex(prev => prev + 1)
        }, 1800)
      }
    } catch (err) {
      console.error('Error completing puzzle:', err)
      showToast('Failed to save puzzle progress', 'error')
    }
  }

  // Navigation handlers
  const goToPrevious = () => {
    if (currentIndex > 1) {
      setJustSolved(false)
      setCurrentIndex(currentIndex - 1)
    }
  }

  const goToNext = () => {
    if (currentIndex < totalCount) {
      setJustSolved(false)
      setCurrentIndex(currentIndex + 1)
    }
  }

  const goToPuzzle = (index: number) => {
    setJustSolved(false)
    setCurrentIndex(index)
  }

  // Reset all progress for this lesson
  const resetProgress = async () => {
    if (!confirm(t('resetProgress'))) {
      return
    }

    setResetting(true)
    try {
      const token = await getToken()
      if (!token) return

      await apiFetch(
        `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/puzzles/reset`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      )

      // Reset local state
      setPuzzles(prev => prev.map(p => ({ ...p, completed: false, attempts: 0 })))
      setCompletedCount(0)
      setCurrentIndex(1)
      setAllComplete(false)
      setJustSolved(false)
    } catch (err) {
      console.error('Error resetting progress:', err)
      showToast(t('resetFailed'), 'error')
    } finally {
      setResetting(false)
    }
  }

  // Get current puzzle
  const currentPuzzle = puzzles.find(p => p.order_index === currentIndex)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error || !currentPuzzle) {
    return (
      <div className="text-center py-8 text-gray-500">
        {error || t('noPuzzles')}
      </div>
    )
  }

  // Progress percentage
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Left: Chess Board with Continue Overlay */}
      <div className="relative flex-1">
        <AnimatedChessBoard
          fen={currentPuzzle.fen}
          solutionMove={currentPuzzle.solution_move}
          onCorrectMove={handlePuzzleComplete}
          onIncorrectMove={(move) => {
            console.log('Incorrect move:', move)
          }}
          showHints={true}
          enableAnimations={true}
          strictValidation={true}
          showStar={false}
        />

      </div>

      {/* Right: Info Panel (Lichess-style) */}
      <div className="lg:w-80 space-y-4">
        {/* Puzzle Info Card */}
        <div className="bg-blue-600 text-white rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="bg-white/20 p-2 rounded">
              <svg className="w-6 h-6" viewBox="0 0 45 45" fill="currentColor">
                <g fillRule="evenodd" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 39h27v-3H9v3zM12 36v-4h21v4H12zM11 14V9h4v2h5V9h5v2h5V9h4v5" strokeLinecap="butt"/>
                  <path d="M34 14l-3 3H14l-3-3"/>
                  <path d="M31 17v12.5H14V17" strokeLinecap="butt" strokeLinejoin="miter"/>
                  <path d="M31 29.5l1.5 2.5h-20l1.5-2.5"/>
                  <path d="M11 14h23" fill="none" strokeLinejoin="miter"/>
                </g>
              </svg>
            </div>
            <div>
              <h3 className="font-bold text-lg">{t('lessonTitle')}</h3>
              <p className="text-sm text-white/80">{t('lessonDescription')}</p>
            </div>
          </div>

          <p className="text-sm bg-white/10 rounded p-3">
            {t('instruction')}
          </p>
        </div>

        {/* Progress */}
        <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">{t('progress')}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">{completedCount}/{totalCount}</span>
              <button
                onClick={resetProgress}
                disabled={resetting || completedCount === 0}
                className="p-1 text-gray-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title={t('resetProgressButton')}
              >
                <RotateCcw className={`w-4 h-4 ${resetting ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
          <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 transition-all duration-500 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Numbered Puzzle Buttons (Lichess-style) */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-6 gap-2">
            {puzzles.map((p) => {
              const isCurrent = p.order_index === currentIndex
              const isCompleted = p.completed

              return (
                <button
                  key={p.id}
                  onClick={() => goToPuzzle(p.order_index)}
                  className={`
                    w-10 h-10 rounded-md text-sm font-semibold transition-all
                    flex items-center justify-center
                    ${isCurrent
                      ? 'bg-blue-600 text-white ring-2 ring-blue-300 ring-offset-1'
                      : isCompleted
                        ? 'bg-green-500 text-white hover:bg-green-600'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }
                  `}
                  title={`${t('puzzleNumber', { number: p.order_index })}${isCompleted ? ` (${t('completed')})` : ''}`}
                >
                  {isCompleted && !isCurrent ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    p.order_index
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* All Complete Celebration */}
        {allComplete && (
          <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <div className="flex items-center gap-3">
              <Trophy className="w-8 h-8 text-green-600" />
              <div>
                <p className="font-semibold text-green-800 dark:text-green-200">
                  {t('allComplete')}
                </p>
                <p className="text-sm text-green-600 dark:text-green-400">
                  {t('masteredAll', { count: totalCount })}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Hint */}
        {currentPuzzle.hint_text && !currentPuzzle.completed && (
          <div className="bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
            <p className="text-sm text-yellow-800 dark:text-yellow-200">
              <span className="font-medium">{t('hint')}</span> {currentPuzzle.hint_text}
            </p>
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between">
          <button
            onClick={goToPrevious}
            disabled={currentIndex <= 1}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-gray-700
                       hover:bg-gray-200 dark:hover:bg-gray-600
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors text-sm font-medium"
          >
            <ChevronLeft className="w-4 h-4" />
            {t('previous')}
          </button>

          <span className="text-sm text-gray-500">
            {currentIndex} / {totalCount}
          </span>

          <button
            onClick={goToNext}
            disabled={currentIndex >= totalCount}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white
                       hover:bg-blue-700
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors text-sm font-medium"
          >
            {t('next')}
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
