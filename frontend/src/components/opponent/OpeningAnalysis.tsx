'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'

interface OpeningData {
  eco: string
  opening: string
  games: number
  wins: number
  losses: number
  draws: number
  win_rate: number
  draw_rate: number
}

interface OpeningAnalysisProps {
  openings: {
    white: OpeningData[]
    black: OpeningData[]
  }
}

export default function OpeningAnalysis({ openings }: OpeningAnalysisProps) {
  const t = useTranslations('opponent')
  const [activeTab, setActiveTab] = useState<'white' | 'black'>('white')

  const currentOpenings = activeTab === 'white' ? openings.white : openings.black

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <span className="text-xl">📖</span>
          {t('openings.title')}
        </h3>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab('white')}
          className={`flex-1 px-4 py-2 text-sm font-medium flex items-center justify-center gap-2 ${
            activeTab === 'white'
              ? 'border-b-2 border-orange-500 text-orange-600 dark:text-orange-400'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          <span className="w-3 h-3 bg-white border border-gray-300 rounded-sm"></span>
          {t('openings.asWhite')}
        </button>
        <button
          onClick={() => setActiveTab('black')}
          className={`flex-1 px-4 py-2 text-sm font-medium flex items-center justify-center gap-2 ${
            activeTab === 'black'
              ? 'border-b-2 border-orange-500 text-orange-600 dark:text-orange-400'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          <span className="w-3 h-3 bg-gray-800 rounded-sm"></span>
          {t('openings.asBlack')}
        </button>
      </div>

      {/* Opening List */}
      <div className="max-h-80 overflow-y-auto">
        {currentOpenings.length > 0 ? (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {currentOpenings.map((opening, index) => (
              <div key={index} className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200">
                        {opening.eco}
                      </span>
                      <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                        {opening.opening || 'Unknown'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {opening.games} {t('openings.games')}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-green-600 dark:text-green-400 font-medium">
                      {opening.win_rate.toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Win/Draw/Loss Bar */}
                <div className="mt-2 flex h-2 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-600">
                  <div
                    className="bg-green-500"
                    style={{ width: `${opening.win_rate}%` }}
                  ></div>
                  <div
                    className="bg-gray-400"
                    style={{ width: `${opening.draw_rate}%` }}
                  ></div>
                  <div
                    className="bg-red-500"
                    style={{ width: `${100 - opening.win_rate - opening.draw_rate}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
            {t('openings.noData')}
          </div>
        )}
      </div>
    </div>
  )
}
