'use client'

import { useTranslations } from 'next-intl'

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

interface PlayerProfileProps {
  player: PlayerData
}

// SVG Pie Chart Component
function PieChart({ wins, losses, draws }: { wins: number; losses: number; draws: number }) {
  const total = wins + losses + draws
  if (total === 0) return null

  const winPercent = (wins / total) * 100
  const drawPercent = (draws / total) * 100
  const lossPercent = (losses / total) * 100

  // Calculate SVG arc paths
  const size = 120
  const center = size / 2
  const radius = 45
  const innerRadius = 28 // For donut chart effect

  const polarToCartesian = (angle: number, r: number) => {
    const angleInRadians = ((angle - 90) * Math.PI) / 180
    return {
      x: center + r * Math.cos(angleInRadians),
      y: center + r * Math.sin(angleInRadians)
    }
  }

  const createArc = (startAngle: number, endAngle: number, r: number, inner: number) => {
    const start = polarToCartesian(startAngle, r)
    const end = polarToCartesian(endAngle, r)
    const innerStart = polarToCartesian(endAngle, inner)
    const innerEnd = polarToCartesian(startAngle, inner)
    const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0

    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y} L ${innerStart.x} ${innerStart.y} A ${inner} ${inner} 0 ${largeArcFlag} 0 ${innerEnd.x} ${innerEnd.y} Z`
  }

  // Calculate angles for each segment
  const winAngle = (winPercent / 100) * 360
  const drawAngle = (drawPercent / 100) * 360
  // const lossAngle = (lossPercent / 100) * 360

  // Create paths - starting from top (0 degrees)
  const winPath = winAngle > 0.1 ? createArc(0, winAngle, radius, innerRadius) : ''
  const drawPath = drawAngle > 0.1 ? createArc(winAngle, winAngle + drawAngle, radius, innerRadius) : ''
  const lossPath = lossPercent > 0.1 ? createArc(winAngle + drawAngle, 360, radius, innerRadius) : ''

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Win segment - Green */}
        {winPath && (
          <path d={winPath} fill="#22c55e" className="transition-all duration-300 hover:opacity-80" />
        )}
        {/* Draw segment - Gray */}
        {drawPath && (
          <path d={drawPath} fill="#9ca3af" className="transition-all duration-300 hover:opacity-80" />
        )}
        {/* Loss segment - Red */}
        {lossPath && (
          <path d={lossPath} fill="#ef4444" className="transition-all duration-300 hover:opacity-80" />
        )}
        {/* Center circle for donut effect */}
        <circle cx={center} cy={center} r={innerRadius - 2} className="fill-white dark:fill-gray-800" />
        {/* Center text */}
        <text x={center} y={center - 4} textAnchor="middle" className="fill-gray-900 dark:fill-white text-xs font-bold">
          {total.toLocaleString()}
        </text>
        <text x={center} y={center + 10} textAnchor="middle" className="fill-gray-500 dark:fill-gray-400 text-[8px]">
          games
        </text>
      </svg>
      {/* Legend */}
      <div className="flex flex-col gap-1.5 text-sm">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-green-500"></span>
          <span className="text-gray-600 dark:text-gray-300">
            {wins.toLocaleString()} <span className="text-gray-400">({winPercent.toFixed(1)}%)</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-gray-400"></span>
          <span className="text-gray-600 dark:text-gray-300">
            {draws.toLocaleString()} <span className="text-gray-400">({drawPercent.toFixed(1)}%)</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-red-500"></span>
          <span className="text-gray-600 dark:text-gray-300">
            {losses.toLocaleString()} <span className="text-gray-400">({lossPercent.toFixed(1)}%)</span>
          </span>
        </div>
      </div>
    </div>
  )
}

export default function PlayerProfile({ player }: PlayerProfileProps) {
  const t = useTranslations('opponent')

  const totalWins = player.wins_white + player.wins_black
  const totalLosses = player.losses_white + player.losses_black

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 mb-6">
        {/* Player Name and Title */}
        <div>
          <div className="flex items-center gap-3">
            {player.title && (
              <span className="bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300 px-3 py-1 rounded-full font-bold text-sm">
                {player.title}
              </span>
            )}
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {player.name}
            </h2>
          </div>
          {player.fide_id && (
            <p className="text-gray-500 dark:text-gray-400 mt-1">
              {t('profile.fideId')}: {player.fide_id}
            </p>
          )}
        </div>

        {/* Pie Chart for Win/Draw/Loss */}
        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
          <PieChart wins={totalWins} losses={totalLosses} draws={player.draws} />
        </div>

        {/* Win Rate Badge */}
        <div className="text-center bg-gradient-to-br from-orange-500 to-orange-600 rounded-lg p-4 text-white">
          <div className="text-4xl font-bold">{player.win_rate.toFixed(1)}%</div>
          <div className="text-orange-100 text-sm">{t('profile.winRate')}</div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {/* Total Games */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {player.total_games.toLocaleString()}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">{t('profile.games')}</div>
        </div>

        {/* Highest ELO */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
            {player.highest_elo || '-'}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">{t('profile.highestElo')}</div>
        </div>

        {/* Latest ELO */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {player.latest_elo || '-'}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">{t('profile.latestElo')}</div>
        </div>

        {/* Wins */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
            {totalWins.toLocaleString()}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {t('stats.winsWhite').split(' ')[0]}
          </div>
        </div>

        {/* Losses */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
            {totalLosses.toLocaleString()}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {t('stats.lossesWhite').split(' ')[0]}
          </div>
        </div>

        {/* Draws */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-gray-600 dark:text-gray-300">
            {player.draws.toLocaleString()}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">{t('stats.draws')}</div>
        </div>
      </div>

      {/* Detailed Stats */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* White Stats */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-4 h-4 bg-white border-2 border-gray-300 rounded"></span>
            {t('filters.white')}
          </h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-green-600 dark:text-green-400 font-medium">{player.wins_white}</span>
              <span className="text-gray-500 dark:text-gray-400"> {t('stats.winsWhite').split('(')[0]}</span>
            </div>
            <div>
              <span className="text-red-600 dark:text-red-400 font-medium">{player.losses_white}</span>
              <span className="text-gray-500 dark:text-gray-400"> {t('stats.lossesWhite').split('(')[0]}</span>
            </div>
          </div>
        </div>

        {/* Black Stats */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-4 h-4 bg-gray-800 border-2 border-gray-600 rounded"></span>
            {t('filters.black')}
          </h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-green-600 dark:text-green-400 font-medium">{player.wins_black}</span>
              <span className="text-gray-500 dark:text-gray-400"> {t('stats.winsBlack').split('(')[0]}</span>
            </div>
            <div>
              <span className="text-red-600 dark:text-red-400 font-medium">{player.losses_black}</span>
              <span className="text-gray-500 dark:text-gray-400"> {t('stats.lossesBlack').split('(')[0]}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Date Range */}
      {(player.first_game_date || player.last_game_date) && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
          {player.first_game_date && (
            <div>
              <span className="font-medium">{t('profile.activeFrom')}:</span> {player.first_game_date}
            </div>
          )}
          {player.last_game_date && (
            <div>
              <span className="font-medium">{t('profile.lastGame')}:</span> {player.last_game_date}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
