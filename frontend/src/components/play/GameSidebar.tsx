import React from 'react'
import { Box, Typography, Paper, Chip } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { tierWorld } from '@/data/bots'
import { playText } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'
import BotAvatar from './BotAvatar'

interface GameSidebarProps {
  bot: Bot
  /** Resolved player color for this game. */
  playerColor: 'w' | 'b'
  thinking: boolean
  gameResult: string | null
  /** Engine still syncing to the local model (shows a subtle chip). */
  syncing?: boolean
  onNewGame: () => void
}

const INK = '#28324E'
const INK_SOFT = '#5C6784'
const GOLD = '#FFC53D'
const GOLD_TEXT = '#6B4A00'
const CARD = '#FFFFFF'

/** Animated "· · ·" dots reused in the thinking speech bubble. */
function ThinkingDots({ color }: { color: string }) {
  return (
    <Box
      component="span"
      aria-hidden="true"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        ml: 0.75,
        '& > span': {
          width: 7,
          height: 7,
          borderRadius: '50%',
          bgcolor: color,
          mr: '4px',
          animation: 'thinkingBounce 1s ease-in-out infinite',
        },
        '& > span:nth-of-type(2)': { animationDelay: '0.15s' },
        '& > span:nth-of-type(3)': { animationDelay: '0.3s', mr: 0 },
        '@keyframes thinkingBounce': {
          '0%, 100%': { opacity: 0.3, transform: 'translateY(0)' },
          '50%': { opacity: 0.9, transform: 'translateY(-3px)' },
        },
      }}
    >
      <span />
      <span />
      <span />
    </Box>
  )
}

/**
 * In-game opponent panel carrying the bot's tier "world" theme: a short gradient
 * banner with an overlapping avatar (desktop) or a compact themed bar (mobile),
 * a themed "thinking…" speech bubble, and a world-colored game-over panel.
 */
export default function GameSidebar({
  bot,
  playerColor,
  thinking,
  gameResult,
  syncing = false,
  onNewGame,
}: GameSidebarProps) {
  const t = useTranslations('bots')
  const world = tierWorld(bot.tier)
  const { main, deep, tint } = world.frame

  const ratingPill = (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        bgcolor: GOLD,
        color: GOLD_TEXT,
        fontFamily: nunito.style.fontFamily,
        fontWeight: 900,
        fontSize: '13px',
        borderRadius: '999px',
        px: '10px',
        py: '3px',
      }}
    >
      ⭐ {bot.rating}
    </Box>
  )

  return (
    <Box data-testid="game-sidebar" data-tier={bot.tier}>
      <Paper
        sx={{
          borderRadius: '20px',
          overflow: 'hidden',
          boxShadow: '0 10px 30px rgba(40,50,78,.10)',
        }}
      >
        {/* Desktop banner with overlapping avatar */}
        <Box
          sx={{
            display: { xs: 'none', md: 'block' },
            position: 'relative',
            height: 86,
            background: world.headerGradient,
          }}
        >
          <Box
            component="span"
            aria-hidden="true"
            sx={{ position: 'absolute', top: 12, right: 16, fontSize: '34px', opacity: 0.35 }}
          >
            {world.emoji}
          </Box>
          <BotAvatar
            bot={bot}
            size={84}
            ringColor="#fff"
            ringWidth={4}
            tint={tint}
            deep={deep}
            thinking={thinking}
            sx={{ position: 'absolute', left: 20, bottom: -38, boxShadow: `0 8px 18px ${deep}4D` }}
          />
        </Box>

        {/* Mobile compact themed bar */}
        <Box
          sx={{
            display: { xs: 'flex', md: 'none' },
            alignItems: 'center',
            gap: 1.5,
            px: 2,
            py: 1.5,
            background: world.headerGradient,
          }}
        >
          <BotAvatar
            bot={bot}
            size={44}
            ringColor="#fff"
            ringWidth={3}
            tint={tint}
            deep={deep}
            thinking={thinking}
          />
          <Box sx={{ minWidth: 0 }}>
            <Typography
              component="div"
              sx={{
                fontFamily: fredoka.style.fontFamily,
                fontWeight: 700,
                fontSize: '18px',
                color: '#fff',
                lineHeight: 1.1,
              }}
            >
              {bot.name}
            </Typography>
            {ratingPill}
          </Box>
        </Box>

        {/* Body */}
        <Box sx={{ px: 2.5, pt: { xs: 2, md: '48px' }, pb: 2.5 }}>
          {/* Name + rating (desktop; mobile shows them in the bar) */}
          <Box
            sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 1.25 }}
          >
            <Typography
              component="h3"
              sx={{
                fontFamily: fredoka.style.fontFamily,
                fontWeight: 700,
                fontSize: '22px',
                color: INK,
                lineHeight: 1.1,
              }}
            >
              {bot.name}
            </Typography>
            {ratingPill}
          </Box>

          {/* Thinking speech bubble */}
          {thinking && (
            <Box
              data-testid="thinking-bubble"
              sx={{
                mt: 1.25,
                bgcolor: tint,
                border: `2px solid ${main}`,
                borderRadius: '12px',
                px: '14px',
                py: '10px',
                fontFamily: nunito.style.fontFamily,
                fontWeight: 800,
                fontSize: '14px',
                color: deep,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {playText(t, 'thinking', `${bot.name} is thinking`, { name: bot.name })}
              <ThinkingDots color={deep} />
            </Box>
          )}

          {syncing && (
            <Chip
              label={playText(t, 'syncingEngine', 'Syncing engine…')}
              size="small"
              variant="outlined"
              sx={{ mt: 1.25 }}
            />
          )}

          {/* Game info */}
          <Box
            sx={{
              mt: 2,
              pt: 1.75,
              borderTop: '2px dashed #DCE8F2',
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '14px',
              color: INK_SOFT,
              display: 'flex',
              justifyContent: 'space-between',
            }}
          >
            <span>{playText(t, 'youPlay', 'You play')}</span>
            <Box component="span" sx={{ color: INK }}>
              {playerColor === 'w'
                ? `♔ ${playText(t, 'white', 'White')}`
                : `♚ ${playText(t, 'black', 'Black')}`}
            </Box>
          </Box>
        </Box>
      </Paper>

      {/* Game-over panel */}
      {gameResult && (
        <Box
          data-testid="game-over-panel"
          sx={{
            mt: 2,
            display: 'flex',
            alignItems: 'center',
            gap: 1.25,
            bgcolor: tint,
            border: `2px solid ${main}`,
            borderRadius: '16px',
            px: 2,
            py: 1.5,
          }}
        >
          <BotAvatar bot={bot} size={40} ringColor={main} ringWidth={2} tint={tint} deep={deep} />
          <Typography
            component="span"
            sx={{
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '15px',
              color: deep,
            }}
          >
            {gameResult}
          </Typography>
        </Box>
      )}

      {/* New Game */}
      <Box
        component="button"
        type="button"
        onClick={onNewGame}
        sx={{
          mt: 2,
          display: 'block',
          width: '100%',
          bgcolor: '#fff',
          border: `2.5px solid ${main}`,
          color: deep,
          fontFamily: nunito.style.fontFamily,
          fontWeight: 800,
          fontSize: '15px',
          borderRadius: '12px',
          py: '12px',
          cursor: 'pointer',
          transition: 'background-color 120ms ease',
          '&:hover': { bgcolor: tint },
        }}
      >
        🔁 {playText(t, 'newGame', 'New game')}
      </Box>
    </Box>
  )
}
