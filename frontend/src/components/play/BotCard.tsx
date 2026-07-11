import React from 'react'
import { Box, Typography } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { botColors } from '@/data/bots'
import { botDescription, botPlayStyle } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'

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
  const { main, deep, tint } = botColors(bot)

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
      {/* Card top: art + rating pill + name banner */}
      <Box sx={{ position: 'relative' }}>
        {bot.avatar ? (
          <Box
            component="img"
            src={bot.avatar}
            alt={bot.name}
            sx={{
              display: 'block',
              width: '100%',
              aspectRatio: '1 / 1',
              objectFit: 'cover',
            }}
          />
        ) : (
          <Box
            aria-hidden="true"
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '100%',
              aspectRatio: '1 / 1',
              bgcolor: tint,
              fontFamily: fredoka.style.fontFamily,
              fontWeight: 700,
              fontSize: '96px',
              lineHeight: 1,
              color: deep,
            }}
          >
            {bot.name[0]}
          </Box>
        )}

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
            background: `linear-gradient(180deg, transparent, color-mix(in srgb, ${deep} 88%, black) 92%)`,
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
            border: `2.5px solid ${main}`,
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
