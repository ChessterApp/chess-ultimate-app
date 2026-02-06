'use client'

import { useTranslations } from 'next-intl'

interface OpponentData {
  name: string
  games: number
  wins: number
  losses: number
  draws: number
  score: string
}

interface FrequentOpponentsProps {
  opponents: OpponentData[]
  onPlayerClick: (playerName: string) => void
}

export default function FrequentOpponents({ opponents, onPlayerClick }: FrequentOpponentsProps) {
  const t = useTranslations('opponent')

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <span className="text-xl">👥</span>
          {t('opponents.title')}
        </h3>
      </div>

      {/* Opponents List */}
      <div className="max-h-80 overflow-y-auto">
        {opponents.length > 0 ? (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {opponents.map((opponent, index) => (
              <button
                key={index}
                onClick={() => onPlayerClick(opponent.name)}
                className="w-full px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-left flex items-center justify-between"
              >
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">
                    {opponent.name}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {opponent.games} {t('opponents.games')}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-medium text-gray-900 dark:text-white">
                    {opponent.score}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    <span className="text-green-600 dark:text-green-400">+{opponent.wins}</span>
                    <span className="mx-1">=</span>
                    <span className="text-gray-500">{opponent.draws}</span>
                    <span className="mx-1">−</span>
                    <span className="text-red-600 dark:text-red-400">{opponent.losses}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
            {t('opponents.noData')}
          </div>
        )}
      </div>
    </div>
  )
}
