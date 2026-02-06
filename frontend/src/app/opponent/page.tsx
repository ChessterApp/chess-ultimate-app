'use client'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import LoadingScreen from '@/components/LoadingScreen'
import PlayerSearch from '@/components/opponent/PlayerSearch'
import PlayerProfile from '@/components/opponent/PlayerProfile'
import GameFilters from '@/components/opponent/GameFilters'
import GamesList from '@/components/opponent/GamesList'
import GameReplayBoard from '@/components/opponent/GameReplayBoard'
import OpeningAnalysis from '@/components/opponent/OpeningAnalysis'
import FrequentOpponents from '@/components/opponent/FrequentOpponents'
import DatabaseStatus from '@/components/opponent/DatabaseStatus'

interface PlayerData {
  name: string
  name_normalized: string
  fide_id: string | null
  title: string | null
  highest_elo: number | null
  latest_elo: number | null
  total_games: number
  wins_white: number
  wins_black: number
  losses_white: number
  losses_black: number
  draws: number
  first_game_date: string | null
  last_game_date: string | null
  win_rate: number
}

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

interface GameFiltersState {
  result: 'all' | 'wins' | 'losses' | 'draws'
  color: 'both' | 'white' | 'black'
  eloMin: string
  eloMax: string
  dateFrom: string
  dateTo: string
  eco: string
}

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

interface OpponentData {
  name: string
  games: number
  wins: number
  losses: number
  draws: number
  score: string
}

interface DatabaseStatusData {
  ready: boolean
  game_count: number
  player_count: number
  indexed_at: string | null
  message: string
}

export default function OpponentAnalysisPage() {
  const t = useTranslations('opponent')

  const [loading, setLoading] = useState(false)
  const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null)
  const [playerData, setPlayerData] = useState<PlayerData | null>(null)
  const [games, setGames] = useState<GameData[]>([])
  const [gamesLoading, setGamesLoading] = useState(false)
  const [totalGames, setTotalGames] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [openings, setOpenings] = useState<{ white: OpeningData[], black: OpeningData[] }>({ white: [], black: [] })
  const [opponents, setOpponents] = useState<OpponentData[]>([])
  const [dbStatus, setDbStatus] = useState<DatabaseStatusData | null>(null)
  const [filters, setFilters] = useState<GameFiltersState>({
    result: 'all',
    color: 'both',
    eloMin: '',
    eloMax: '',
    dateFrom: '',
    dateTo: '',
    eco: ''
  })
  const [selectedGame, setSelectedGame] = useState<{ game: GameData; pgn: string } | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

  // Fetch database status on mount
  useEffect(() => {
    async function fetchStatus() {
      try {
        const response = await fetch(`${API_URL}/api/opponent/status`)
        if (response.ok) {
          const data = await response.json()
          setDbStatus(data)
        }
      } catch (error) {
        console.error('Failed to fetch database status:', error)
      }
    }
    fetchStatus()
  }, [API_URL])

  // Fetch player profile
  const fetchPlayerProfile = useCallback(async (playerName: string) => {
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/opponent/${encodeURIComponent(playerName)}/profile`)
      if (response.ok) {
        const data = await response.json()
        // Flatten the API response to match PlayerData interface
        // API returns stats nested in 'stats' object, but component expects flat structure
        const flattenedData: PlayerData = {
          name: data.name,
          name_normalized: data.name_normalized || '',
          fide_id: data.fide_id,
          title: data.title,
          highest_elo: data.highest_elo,
          latest_elo: data.latest_elo,
          total_games: data.total_games,
          wins_white: data.stats?.wins_white ?? 0,
          wins_black: data.stats?.wins_black ?? 0,
          losses_white: data.stats?.losses_white ?? 0,
          losses_black: data.stats?.losses_black ?? 0,
          draws: data.stats?.draws ?? 0,
          first_game_date: data.first_game || null,
          last_game_date: data.last_game || null,
          win_rate: data.stats?.win_rate ?? 0
        }
        setPlayerData(flattenedData)
        setSelectedPlayer(playerName)
      } else {
        console.error('Failed to fetch player profile')
        setPlayerData(null)
      }
    } catch (error) {
      console.error('Error fetching player profile:', error)
      setPlayerData(null)
    } finally {
      setLoading(false)
    }
  }, [API_URL])

  // Fetch games with filters
  const fetchGames = useCallback(async (page: number = 1) => {
    if (!selectedPlayer) return

    setGamesLoading(true)
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '20'
      })

      if (filters.result !== 'all') params.set('result', filters.result)
      if (filters.color !== 'both') params.set('color', filters.color)
      if (filters.eloMin) params.set('elo_min', filters.eloMin)
      if (filters.eloMax) params.set('elo_max', filters.eloMax)
      if (filters.dateFrom) params.set('date_from', filters.dateFrom)
      if (filters.dateTo) params.set('date_to', filters.dateTo)
      if (filters.eco) params.set('eco', filters.eco)

      const response = await fetch(
        `${API_URL}/api/opponent/${encodeURIComponent(selectedPlayer)}/games?${params}`
      )

      if (response.ok) {
        const data = await response.json()
        // Transform games from API format (nested white/black objects) to flat format
        const transformedGames: GameData[] = data.games.map((game: {
          id: number
          white: { name: string; elo: number | null; title: string | null }
          black: { name: string; elo: number | null; title: string | null }
          result: string
          date: string
          eco: string
          opening: string
          event: string
          site: string
        }) => ({
          id: game.id,
          white_name: game.white.name,
          black_name: game.black.name,
          white_elo: game.white.elo,
          black_elo: game.black.elo,
          result: game.result,
          date: game.date,
          eco: game.eco,
          opening: game.opening,
          event: game.event,
          site: game.site
        }))
        setGames(transformedGames)
        // API returns pagination in nested object
        setTotalGames(data.pagination?.total ?? data.total ?? 0)
        setCurrentPage(data.pagination?.page ?? data.page ?? page)
      }
    } catch (error) {
      console.error('Error fetching games:', error)
    } finally {
      setGamesLoading(false)
    }
  }, [selectedPlayer, filters, API_URL])

  // Fetch openings (fetch both white and black separately)
  const fetchOpenings = useCallback(async () => {
    if (!selectedPlayer) return

    try {
      // Fetch white openings
      const whiteResponse = await fetch(
        `${API_URL}/api/opponent/${encodeURIComponent(selectedPlayer)}/openings?color=white`
      )
      // Fetch black openings
      const blackResponse = await fetch(
        `${API_URL}/api/opponent/${encodeURIComponent(selectedPlayer)}/openings?color=black`
      )

      const whiteData = whiteResponse.ok ? await whiteResponse.json() : { openings: [] }
      const blackData = blackResponse.ok ? await blackResponse.json() : { openings: [] }

      setOpenings({
        white: whiteData.openings || [],
        black: blackData.openings || []
      })
    } catch (error) {
      console.error('Error fetching openings:', error)
    }
  }, [selectedPlayer, API_URL])

  // Fetch frequent opponents
  const fetchOpponents = useCallback(async () => {
    if (!selectedPlayer) return

    try {
      const response = await fetch(
        `${API_URL}/api/opponent/${encodeURIComponent(selectedPlayer)}/opponents`
      )

      if (response.ok) {
        const data = await response.json()
        // Transform API response to add score field
        const transformedOpponents: OpponentData[] = (data.opponents || []).map((opp: {
          name: string
          games: number
          wins: number
          losses: number
          draws: number
          win_rate: number
        }) => ({
          name: opp.name,
          games: opp.games,
          wins: opp.wins,
          losses: opp.losses,
          draws: opp.draws,
          // Calculate chess score: 1 point for win, 0.5 for draw
          score: `${opp.wins + opp.draws * 0.5}/${opp.games}`
        }))
        setOpponents(transformedOpponents)
      }
    } catch (error) {
      console.error('Error fetching opponents:', error)
    }
  }, [selectedPlayer, API_URL])

  // Load all data when player is selected
  useEffect(() => {
    if (selectedPlayer) {
      fetchGames(1)
      fetchOpenings()
      fetchOpponents()
    }
  }, [selectedPlayer, fetchGames, fetchOpenings, fetchOpponents])

  // Reload games when filters change
  useEffect(() => {
    if (selectedPlayer) {
      fetchGames(1)
    }
  }, [filters, selectedPlayer, fetchGames])

  const handlePlayerSelect = (playerName: string) => {
    setFilters({
      result: 'all',
      color: 'both',
      eloMin: '',
      eloMax: '',
      dateFrom: '',
      dateTo: '',
      eco: ''
    })
    fetchPlayerProfile(playerName)
  }

  const handleFilterChange = (newFilters: GameFiltersState) => {
    setFilters(newFilters)
  }

  const handlePageChange = (page: number) => {
    fetchGames(page)
  }

  const handleSelectGame = (game: GameData, pgn: string) => {
    setSelectedGame({ game, pgn })
  }

  const handleCloseReplay = () => {
    setSelectedGame(null)
  }

  if (loading) {
    return <LoadingScreen isVisible={true} />
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">{t('title')}</h1>
        <p className="text-gray-600 dark:text-gray-300">{t('subtitle')}</p>
      </div>

      {/* Database Status */}
      {dbStatus && (
        <DatabaseStatus status={dbStatus} />
      )}

      {/* Player Search */}
      <div className="mb-8">
        <PlayerSearch onSelect={handlePlayerSelect} />
      </div>

      {/* Player Profile and Analysis */}
      {playerData && (
        <div className="space-y-8">
          {/* Player Profile Card */}
          <PlayerProfile player={playerData} />

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left Column: Board (when game selected) or Filters and Games */}
            <div className="lg:col-span-2 space-y-6">
              {/* Game Replay Board */}
              {selectedGame && (
                <GameReplayBoard
                  pgn={selectedGame.pgn}
                  gameInfo={{
                    white_name: selectedGame.game.white_name,
                    black_name: selectedGame.game.black_name,
                    white_elo: selectedGame.game.white_elo,
                    black_elo: selectedGame.game.black_elo,
                    result: selectedGame.game.result,
                    date: selectedGame.game.date,
                    event: selectedGame.game.event,
                    eco: selectedGame.game.eco
                  }}
                  playerName={selectedPlayer || ''}
                  onClose={handleCloseReplay}
                />
              )}

              {/* Game Filters */}
              <GameFilters
                filters={filters}
                onChange={handleFilterChange}
              />

              {/* Games List */}
              <GamesList
                games={games}
                loading={gamesLoading}
                playerName={selectedPlayer || ''}
                currentPage={currentPage}
                totalGames={totalGames}
                onPageChange={handlePageChange}
                onSelectGame={handleSelectGame}
                selectedGameId={selectedGame?.game.id || null}
              />
            </div>

            {/* Right Column: Analysis */}
            <div className="space-y-6">
              {/* Opening Analysis */}
              <OpeningAnalysis openings={openings} />

              {/* Frequent Opponents */}
              <FrequentOpponents
                opponents={opponents}
                onPlayerClick={handlePlayerSelect}
              />
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!playerData && !loading && (
        <div className="text-center py-16 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div className="text-6xl mb-4">🔍</div>
          <p className="text-xl text-gray-600 dark:text-gray-300">
            {t('noResults')}
          </p>
          <p className="text-gray-500 mt-2">
            {t('tryDifferent')}
          </p>
        </div>
      )}
    </div>
  )
}
