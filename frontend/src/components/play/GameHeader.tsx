import React from 'react'
import { Box, Typography } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { gameTheme } from '@/data/bots'
import { playText, worldName } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'
import BotAvatar from './BotAvatar'

interface GameHeaderProps {
  bot: Bot
  /** Show the animated "thinking…" speech bubble (always mounted, toggled via visibility). */
  thinking: boolean
  /** Engine still syncing to the local model (shows a subtle pill). */
  syncing?: boolean
}

const GOLD = '#FFC53D'
const GOLD_TEXT = '#6B4A00'

/** Animated "· · ·" dots for the thinking speech bubble. */
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
          width: 6,
          height: 6,
          borderRadius: '50%',
          bgcolor: color,
          ml: '3px',
          animation: 'thinkingBounce 1s ease-in-out infinite',
        },
        '& > span:nth-of-type(2)': { animationDelay: '0.15s' },
        '& > span:nth-of-type(3)': { animationDelay: '0.3s' },
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
 * V3 "Immersive World" bot header: a rounded-square avatar, the bot name in
 * white Fredoka with a soft shadow, a gold rating pill and a translucent world
 * "ghost" pill, and — while the bot is thinking — a white speech bubble.
 */
export default function GameHeader({ bot, thinking, syncing = false }: GameHeaderProps) {
  const t = useTranslations('bots')
  const theme = gameTheme(bot)
  const { deep, tint } = theme

  return (
    <Box data-testid="game-header" data-tier={bot.tier}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.75 }}>
        <BotAvatar
          bot={bot}
          size={88}
          ringColor="rgba(255,255,255,.9)"
          ringWidth={4}
          tint={tint}
          deep={deep}
          thinking={thinking}
          sx={{
            borderRadius: '28px',
            transform: 'rotate(-3deg)',
            boxShadow: `0 10px 26px ${deep}59`,
          }}
        />
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h2"
            sx={{
              fontFamily: fredoka.style.fontFamily,
              fontWeight: 700,
              fontSize: '28px',
              color: '#fff',
              lineHeight: 1,
              textShadow: `0 2px 8px ${deep}59`,
            }}
          >
            {bot.name}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mt: 0.9, flexWrap: 'wrap' }}>
            <Box
              component="span"
              sx={{
                bgcolor: GOLD,
                color: GOLD_TEXT,
                fontFamily: nunito.style.fontFamily,
                fontWeight: 900,
                fontSize: '13px',
                borderRadius: '999px',
                px: '11px',
                py: '4px',
              }}
            >
              ⭐ {bot.rating}
            </Box>
            <Box
              component="span"
              sx={{
                bgcolor: 'rgba(255,255,255,.25)',
                color: '#fff',
                backdropFilter: 'blur(4px)',
                fontFamily: nunito.style.fontFamily,
                fontWeight: 900,
                fontSize: '13px',
                borderRadius: '999px',
                px: '11px',
                py: '4px',
              }}
            >
              {theme.worldEmoji} {worldName(t, bot.tier)}
            </Box>
            {syncing && (
              <Box
                component="span"
                data-testid="syncing-pill"
                sx={{
                  bgcolor: 'rgba(255,255,255,.25)',
                  color: '#fff',
                  backdropFilter: 'blur(4px)',
                  fontFamily: nunito.style.fontFamily,
                  fontWeight: 900,
                  fontSize: '13px',
                  borderRadius: '999px',
                  px: '11px',
                  py: '4px',
                }}
              >
                {playText(t, 'syncingEngine', 'Syncing engine…')}
              </Box>
            )}
          </Box>
        </Box>
      </Box>

      {/* Always mounted so the header keeps a constant height — a conditional
          mount here shifts the board below on every bot move. */}
      <Box
        data-testid="thinking-bubble"
        data-thinking={thinking}
        aria-hidden={!thinking}
        sx={{
          mt: 1.75,
          bgcolor: '#fff',
          borderRadius: '16px 16px 16px 4px',
          px: '14px',
          py: '10px',
          fontFamily: nunito.style.fontFamily,
          fontWeight: 800,
          fontSize: '14px',
          color: deep,
          boxShadow: `0 6px 18px ${deep}33`,
          display: 'inline-flex',
          alignItems: 'center',
          visibility: thinking ? 'visible' : 'hidden',
          opacity: thinking ? 1 : 0,
          transition: 'opacity 150ms ease',
        }}
      >
        {playText(t, 'thinking', `${bot.name} is thinking`, { name: bot.name })}
        <ThinkingDots color={deep} />
      </Box>
    </Box>
  )
}
