'use client'

import { useTranslations } from 'next-intl'

interface DatabaseStatusData {
  ready?: boolean
  indexed?: boolean
  game_count: number
  player_count: number
  indexed_at: string | null
  message?: string
}

interface DatabaseStatusProps {
  status: DatabaseStatusData
}

export default function DatabaseStatus({ status }: DatabaseStatusProps) {
  const t = useTranslations('opponent')

  // API returns 'indexed' field, support both for compatibility
  const isReady = status.ready || status.indexed

  if (isReady) {
    return (
      <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></span>
          <div>
            <span className="text-green-800 dark:text-green-200 font-medium">
              {t('database.ready')}
            </span>
            <span className="text-green-600 dark:text-green-400 text-sm ml-2">
              {status.game_count.toLocaleString()} {t('database.totalGames').toLowerCase()} • {status.player_count.toLocaleString()} {t('database.totalPlayers').toLowerCase()}
            </span>
          </div>
        </div>
        {status.indexed_at && (
          <span className="text-xs text-green-600 dark:text-green-400">
            {t('database.lastUpdated')}: {new Date(status.indexed_at).toLocaleDateString()}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="mb-6 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg px-4 py-3 flex items-center gap-3">
      <svg className="animate-spin h-5 w-5 text-yellow-600" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <div>
        <span className="text-yellow-800 dark:text-yellow-200 font-medium">
          {t('database.indexing')}
        </span>
        <span className="text-yellow-600 dark:text-yellow-400 text-sm ml-2">
          {status.message}
        </span>
      </div>
    </div>
  )
}
