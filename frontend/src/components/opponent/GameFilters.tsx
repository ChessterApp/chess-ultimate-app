'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'

interface GameFiltersState {
  result: 'all' | 'wins' | 'losses' | 'draws'
  color: 'both' | 'white' | 'black'
  eloMin: string
  eloMax: string
  dateFrom: string
  dateTo: string
  eco: string
}

interface GameFiltersProps {
  filters: GameFiltersState
  onChange: (filters: GameFiltersState) => void
}

export default function GameFilters({ filters, onChange }: GameFiltersProps) {
  const t = useTranslations('opponent')
  const [isExpanded, setIsExpanded] = useState(false)

  const handleChange = (key: keyof GameFiltersState, value: string) => {
    onChange({ ...filters, [key]: value })
  }

  const handleReset = () => {
    onChange({
      result: 'all',
      color: 'both',
      eloMin: '',
      eloMax: '',
      dateFrom: '',
      dateTo: '',
      eco: ''
    })
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          {t('filters.title')}
        </h3>
        <svg
          className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Quick Filters (Always Visible) */}
      <div className="mt-4 flex flex-wrap gap-2">
        {/* Result Filter */}
        <div className="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600">
          {(['all', 'wins', 'losses', 'draws'] as const).map((value) => (
            <button
              key={value}
              onClick={() => handleChange('result', value)}
              className={`px-3 py-1 text-sm ${
                filters.result === value
                  ? 'bg-orange-500 text-white'
                  : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
              }`}
            >
              {t(`filters.${value}`)}
            </button>
          ))}
        </div>

        {/* Color Filter */}
        <div className="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600">
          {(['both', 'white', 'black'] as const).map((value) => (
            <button
              key={value}
              onClick={() => handleChange('color', value)}
              className={`px-3 py-1 text-sm flex items-center gap-1 ${
                filters.color === value
                  ? 'bg-orange-500 text-white'
                  : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
              }`}
            >
              {value === 'white' && <span className="w-3 h-3 bg-white border border-gray-300 rounded-sm"></span>}
              {value === 'black' && <span className="w-3 h-3 bg-gray-800 rounded-sm"></span>}
              {t(`filters.${value}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Expanded Filters */}
      {isExpanded && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          {/* ELO Range */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('filters.eloMin')}
            </label>
            <input
              type="number"
              value={filters.eloMin}
              onChange={(e) => handleChange('eloMin', e.target.value)}
              placeholder="1000"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('filters.eloMax')}
            </label>
            <input
              type="number"
              value={filters.eloMax}
              onChange={(e) => handleChange('eloMax', e.target.value)}
              placeholder="2800"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>

          {/* ECO Code */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('filters.eco')}
            </label>
            <input
              type="text"
              value={filters.eco}
              onChange={(e) => handleChange('eco', e.target.value.toUpperCase())}
              placeholder="B90"
              maxLength={3}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white uppercase"
            />
          </div>

          {/* Date Range */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('filters.dateFrom')}
            </label>
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(e) => handleChange('dateFrom', e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('filters.dateTo')}
            </label>
            <input
              type="date"
              value={filters.dateTo}
              onChange={(e) => handleChange('dateTo', e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
          </div>

          {/* Reset Button */}
          <div className="flex items-end">
            <button
              onClick={handleReset}
              className="w-full px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              {t('filters.reset')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
