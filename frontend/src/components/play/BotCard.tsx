import React from 'react'
import { Box, Typography } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { tierWorld } from '@/data/bots'
import { botDescription, botPlayStyle } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'
import WorldScenery from './WorldScenery'

interface BotCardProps {
  bot: Bot
  selected?: boolean
  onClick: () => void
}

const INK = '#28324E'
const INK_SOFT = '#5C6784'
const GOLD = '#FFC53D'
const GOLD_TEXT = '#6B4A00'

export default function BotCard({ bot, selected = false, onClick }: BotCardProps) {
  const t = useTranslations('bots')
  const world = tierWorld(bot.tier)
  // World frame themes the whole tier (border + card tint); beginner heroes keep
  // their personal signature colors on the name banner + chip so the four stay
  // distinct, everyone else inherits the world frame.
  const { main, deep, tint } = world.frame
  const signature = bot.colors ?? world.frame

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onClick()
    }
  }

  return (
    <Box
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      sx={{
        cursor: 'pointer',
        borderRadius: '26px',
        overflow: 'hidden',
        bgcolor: tint,
        border: `5px solid ${main}`,
        boxShadow: '0 14px 30px rgba(40,50,78,.14)',
        transition: 'transform 150ms ease, box-shadow 150ms ease',
        transform: selected ? 'scale(1.02)' : 'none',
        ...(selected && {
          boxShadow: `0 0 0 4px ${main}66, 0 18px 36px rgba(40,50,78,.20)`,
        }),
        '&:hover': {
          transform: selected ? 'scale(1.02) translateY(-4px)' : 'translateY(-4px)',
          boxShadow: `0 22px 40px rgba(40,50,78,.22)`,
        },
        '&:focus-visible': {
          outline: `3px solid ${main}`,
          outlineOffset: '2px',
        },
        '@media (prefers-reduced-motion: reduce)': {
          transition: 'none',
          transform: 'none',
          '&:hover': { transform: 'none' },
        },
      }}
    >
      {/* Card top: world scenery + art + rating pill + name banner */}
      <Box sx={{ position: 'relative' }}>
        {/* Square art slot — world scenery painted behind every card */}
        <Box sx={{ position: 'relative', width: '100%', aspectRatio: '1 / 1' }}>
          <WorldScenery tier={bot.tier} />

          {bot.avatar ? (
            <Box
              component="img"
              src={bot.avatar}
              alt={bot.name}
              sx={{
                position: 'relative',
                display: 'block',
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
          ) : (
            /* Friendly silhouette placeholder — drop-in art slot for bots whose
               character image is not ready yet. */
            <Box
              data-testid="bot-placeholder"
              sx={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '14px',
              }}
            >
              <Box
                component="svg"
                viewBox="0 0 100 100"
                aria-hidden="true"
                sx={{ width: '46%', height: 'auto', filter: 'drop-shadow(0 4px 6px rgba(40,50,78,.2))' }}
              >
                {/* Rounded pawn — a friendly, world-neutral stand-in */}
                <circle cx="50" cy="30" r="16" fill="#FFFFFF" opacity="0.92" />
                <path
                  d="M32 82 C32 60 44 52 50 52 C56 52 68 60 68 82 Z"
                  fill="#FFFFFF"
                  opacity="0.92"
                />
              </Box>
              <Box
                component="span"
                sx={{
                  bgcolor: 'rgba(255,255,255,0.9)',
                  color: deep,
                  fontFamily: nunito.style.fontFamily,
                  fontWeight: 800,
                  fontSize: '13px',
                  borderRadius: '999px',
                  px: '12px',
                  py: '4px',
                  boxShadow: '0 2px 6px rgba(40,50,78,.18)',
                }}
              >
                {t.has('artComingSoon') ? t('artComingSoon') : 'Art coming soon'}
              </Box>
            </Box>
          )}
        </Box>

        {/* Rating pill */}
        <Box
          sx={{
            position: 'absolute',
            top: 12,
            left: 12,
            bgcolor: GOLD,
            color: GOLD_TEXT,
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '16px',
            borderRadius: '999px',
            px: '14px',
            py: '6px',
            boxShadow: '0 3px 8px rgba(40,50,78,.25)',
          }}
        >
          ⭐ {bot.rating}
        </Box>

        {/* Name banner */}
        <Box
          sx={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            padding: '34px 16px 10px',
            background: `linear-gradient(180deg, transparent, color-mix(in srgb, ${signature.deep} 88%, black) 92%)`,
          }}
        >
          <Typography
            component="div"
            sx={{
              fontFamily: fredoka.style.fontFamily,
              fontWeight: 700,
              fontSize: '32px',
              lineHeight: 1.1,
              color: '#fff',
            }}
          >
            {bot.name}
          </Typography>
        </Box>
      </Box>

      {/* Body: description + play-style chip */}
      <Box sx={{ padding: '16px 18px 20px' }}>
        <Typography
          component="p"
          sx={{
            fontFamily: nunito.style.fontFamily,
            fontSize: '15.5px',
            fontWeight: 700,
            color: INK_SOFT,
            lineHeight: 1.45,
            minHeight: '66px',
          }}
        >
          {botDescription(t, bot)}
        </Typography>

        <Box
          component="span"
          sx={{
            display: 'inline-block',
            mt: '10px',
            bgcolor: '#fff',
            border: `2.5px solid ${signature.main}`,
            color: INK,
            borderRadius: '999px',
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '15px',
            padding: '6px 16px',
          }}
        >
          {bot.emoji ? `${bot.emoji} ` : ''}
          {botPlayStyle(t, bot)}
        </Box>
      </Box>
    </Box>
  )
}
