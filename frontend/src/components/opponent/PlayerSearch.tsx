'use client'

import { useState, useEffect, useRef } from 'react'
import { useTranslations } from 'next-intl'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'

interface SearchResult {
  name: string
  name_normalized: string
  total_games: number
  highest_elo: number | null
  title: string | null
}

interface PlayerSearchProps {
  onSelect: (playerName: string) => void
}

export default function PlayerSearch({ onSelect }: PlayerSearchProps) {
  const t = useTranslations('opponent')
  const { showToast } = useToast()

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Search debounce
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (query.length >= 2) {
        setLoading(true)
        try {
          const data = await apiFetch<any>(
            `${API_URL}/api/opponent/search?q=${encodeURIComponent(query)}&limit=10`
          )
          // API returns array directly, not wrapped in { players: [...] }
          setResults(Array.isArray(data) ? data : (data.players || []))
          setIsOpen(true)
        } catch (error) {
          console.error('Search error:', error)
          if (error instanceof ApiError) {
            if (error.status === 429) {
              showToast('Too many requests — please slow down', 'error')
            } else if (error.status === 0) {
              showToast('Network error — check your connection', 'error')
            }
          }
          setResults([])
        } finally {
          setLoading(false)
        }
      } else {
        setResults([])
        setIsOpen(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [query, API_URL])

  const handleSelect = (player: SearchResult) => {
    setQuery(player.name)
    setIsOpen(false)
    onSelect(player.name)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (results.length > 0) {
      handleSelect(results[0])
    } else if (query.length >= 2) {
      onSelect(query)
    }
  }

  return (
    <div ref={wrapperRef} className="relative max-w-xl">
      <form onSubmit={handleSubmit}>
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="w-full px-4 py-3 pl-12 pr-24 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
          />
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <button
            type="submit"
            className="absolute inset-y-0 right-0 px-4 flex items-center bg-orange-500 hover:bg-orange-600 text-white rounded-r-lg transition-colors"
          >
            {loading ? (
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              t('searchButton')
            )}
          </button>
        </div>
      </form>

      {/* Autocomplete Dropdown */}
      {isOpen && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 max-h-96 overflow-y-auto">
          {results.map((player, index) => (
            <button
              key={index}
              onClick={() => handleSelect(player)}
              className="w-full px-4 py-3 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-between border-b border-gray-100 dark:border-gray-700 last:border-0"
            >
              <div>
                <div className="flex items-center gap-2">
                  {player.title && (
                    <span className="text-orange-600 dark:text-orange-400 font-semibold text-sm">
                      {player.title}
                    </span>
                  )}
                  <span className="font-medium text-gray-900 dark:text-white">
                    {player.name}
                  </span>
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {player.total_games.toLocaleString()} games
                  {player.highest_elo && ` • Peak: ${player.highest_elo}`}
                </div>
              </div>
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
