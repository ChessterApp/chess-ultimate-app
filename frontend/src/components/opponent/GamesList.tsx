'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'

interface GameData {
  id: number
  white_name: string
  black_name: string
  white_elo: number | null
  black_elo: number | null
  result: string
  date: string
  eco: string
  opening: string
  event: string
  site: string
}

interface GamesListProps {
  games: GameData[]
  loading: boolean
  playerName: string
  currentPage: number
  totalGames: number
  onPageChange: (page: number) => void
  onSelectGame?: (game: GameData, pgn: string) => void
  selectedGameId?: number | null
}

export default function GamesList({
  games,
  loading,
  playerName,
  currentPage,
  totalGames,
  onPageChange,
  onSelectGame,
  selectedGameId
}: GamesListProps) {
  const t = useTranslations('opponent')
  const tCommon = useTranslations('common')
  const { showToast } = useToast()
  const [loadingGameId, setLoadingGameId] = useState<number | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ''
  const gamesPerPage = 20
  const totalPages = Math.ceil(totalGames / gamesPerPage)

  const getPlayerResult = (game: GameData) => {
    const playerIsWhite = game.white_name.toLowerCase() === playerName.toLowerCase()
    if (game.result === '1/2-1/2') return '='
    if (game.result === '1-0') return playerIsWhite ? 'W' : 'L'
    if (game.result === '0-1') return playerIsWhite ? 'L' : 'W'
    return '*'
  }

  const handleReplayGame = async (game: GameData) => {
    if (!onSelectGame) return

    setLoadingGameId(game.id)
    try {
      const data = await apiFetch<any>(`${API_URL}/api/opponent/game/${game.id}/pgn`)
      onSelectGame(game, data.pgn)
    } catch (error) {
      console.error('Error fetching PGN:', error)
      if (error instanceof ApiError) {
        if (error.status === 0) {
          showToast('Network error — check your connection', 'error')
        } else {
          showToast('Failed to load game — please try again', 'error')
        }
      }
    } finally {
      setLoadingGameId(null)
    }
  }

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div className="animate-pulse space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h3 className="font-semibold text-gray-900 dark:text-white">
          {t('games.title')} ({totalGames.toLocaleString()})
        </h3>
      </div>

      {/* Games Table */}
      {games.length > 0 ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    {t('games.opponent')}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    {t('games.result')}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider hidden md:table-cell">
                    {t('games.eco')}
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider hidden lg:table-cell">
                    {t('games.event')}
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    {t('games.date')}
                  </th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {games.map((game) => {
                  const playerIsWhite = game.white_name.toLowerCase() === playerName.toLowerCase()
                  const opponent = playerIsWhite ? game.black_name : game.white_name
                  const opponentElo = playerIsWhite ? game.black_elo : game.white_elo
                  const playerResult = getPlayerResult(game)

                  const isSelected = selectedGameId === game.id
                  const isLoading = loadingGameId === game.id

                  return (
                    <tr
                      key={game.id}
                      className={`${isSelected ? 'bg-orange-50 dark:bg-orange-900/20' : ''} ${onSelectGame ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50' : ''}`}
                      onClick={() => onSelectGame && handleReplayGame(game)}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-3 h-3 rounded-sm ${playerIsWhite ? 'bg-white border border-gray-300' : 'bg-gray-800'}`}></span>
                          <div>
                            <div className="font-medium text-gray-900 dark:text-white">{opponent}</div>
                            {opponentElo && (
                              <div className="text-sm text-gray-500 dark:text-gray-400">{opponentElo}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`font-bold text-lg ${
                          playerResult === 'W' ? 'text-green-600 dark:text-green-400' :
                          playerResult === 'L' ? 'text-red-600 dark:text-red-400' :
                          'text-gray-600 dark:text-gray-400'
                        }`}>
                          {playerResult}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center hidden md:table-cell">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200">
                          {game.eco || '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        <div className="max-w-xs truncate text-sm text-gray-600 dark:text-gray-400">
                          {game.event || '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
                        {game.date || '-'}
                      </td>
                      <td className="px-4 py-3">
                        {onSelectGame ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleReplayGame(game)
                            }}
                            disabled={isLoading}
                            className={`flex items-center gap-1 text-sm font-medium ${
                              isSelected
                                ? 'text-orange-700 dark:text-orange-300'
                                : 'text-orange-600 hover:text-orange-700 dark:text-orange-400 dark:hover:text-orange-300'
                            }`}
                          >
                            {isLoading ? (
                              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M8 5v14l11-7z" />
                              </svg>
                            )}
                            {t('games.replay')}
                          </button>
                        ) : (
                          <span className="text-gray-400 text-sm">{game.eco}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                {tCommon('page', { current: currentPage, total: totalPages })}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => onPageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  {tCommon('previous')}
                </button>
                <button
                  onClick={() => onPageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  {tCommon('next')}
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
          {t('games.noGames')}
        </div>
      )}
    </div>
  )
}
