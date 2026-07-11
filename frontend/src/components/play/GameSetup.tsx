import React from 'react'
import { Box, Typography, Paper } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { tierWorld } from '@/data/bots'
import { botDescription, playText, tierLabel, worldName } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'
import BotAvatar from './BotAvatar'

type PlayerColor = 'white' | 'black' | 'random'

interface GameSetupProps {
  bot: Bot
  playerColor: PlayerColor
  onColorChange: (color: PlayerColor) => void
  onPlay: () => void
  onChangeBot: () => void
  disabled?: boolean
}

const INK = '#28324E'
const INK_SOFT = '#5C6784'
const GOLD = '#FFC53D'
const GOLD_TEXT = '#6B4A00'
const CARD = '#FFFFFF'

const COLOR_OPTIONS: { value: PlayerColor; glyph: string; labelKey: string; fallback: string }[] = [
  { value: 'white', glyph: '♔', labelKey: 'white', fallback: 'White' },
  { value: 'random', glyph: '🎲', labelKey: 'random', fallback: 'Random' },
  { value: 'black', glyph: '♚', labelKey: 'black', fallback: 'Black' },
]

export default function GameSetup({
  bot,
  playerColor,
  onColorChange,
  onPlay,
  onChangeBot,
  disabled = false,
}: GameSetupProps) {
  const t = useTranslations('bots')
  const world = tierWorld(bot.tier)
  const { main, deep, tint } = world.frame

  return (
    <Paper
      sx={{
        maxWidth: 660,
        mx: 'auto',
        borderRadius: '24px',
        overflow: 'hidden',
        boxShadow: '0 14px 40px rgba(40,50,78,.10)',
      }}
    >
      {/* World banner with overlapping avatar */}
      <Box
        sx={{
          position: 'relative',
          height: 190,
          background: world.headerGradient,
        }}
      >
        {/* World / league label */}
        <Box
          sx={{
            position: 'absolute',
            top: 18,
            left: 22,
            display: 'inline-block',
            bgcolor: 'rgba(255,255,255,0.28)',
            color: '#fff',
            fontFamily: nunito.style.fontFamily,
            fontWeight: 900,
            fontSize: '13px',
            letterSpacing: '0.3px',
            textTransform: 'uppercase',
            borderRadius: '999px',
            px: '14px',
            py: '6px',
          }}
        >
          <Box component="span" aria-hidden="true" sx={{ mr: 0.75 }}>
            {world.emoji}
          </Box>
          {worldName(t, bot.tier)} · {tierLabel(t, bot.tier)}
        </Box>

        {/* Change bot (back) */}
        <Box
          component="button"
          type="button"
          onClick={onChangeBot}
          sx={{
            position: 'absolute',
            top: 18,
            right: 22,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#fff',
            opacity: 0.9,
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '14px',
            '&:hover': { opacity: 1 },
          }}
        >
          {playText(t, 'changeBot', 'Change bot')} ↺
        </Box>

        {/* Wave edge */}
        <Box
          component="svg"
          viewBox="0 0 1440 54"
          preserveAspectRatio="none"
          aria-hidden="true"
          sx={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: -1,
            width: '100%',
            height: 34,
            display: 'block',
          }}
        >
          <path
            d="M0,30 C240,55 480,0 720,22 C960,44 1200,10 1440,32 L1440,54 L0,54 Z"
            fill={CARD}
          />
        </Box>

        {/* Overlapping avatar */}
        <BotAvatar
          bot={bot}
          size={164}
          ringColor="#fff"
          ringWidth={6}
          tint={tint}
          deep={deep}
          sx={{
            position: 'absolute',
            left: '50%',
            bottom: -72,
            transform: 'translateX(-50%)',
            boxShadow: `0 12px 28px ${deep}59`,
          }}
        />
      </Box>

      {/* Card body */}
      <Box sx={{ px: { xs: 3, sm: '44px' }, pt: '88px', pb: '40px', textAlign: 'center', bgcolor: CARD }}>
        <Typography
          component="h2"
          sx={{
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 700,
            fontSize: '36px',
            lineHeight: 1.1,
            color: INK,
          }}
        >
          {bot.name}
        </Typography>

        <Box sx={{ mt: 1, mb: 0.75 }}>
          <Box
            component="span"
            sx={{
              display: 'inline-block',
              bgcolor: GOLD,
              color: GOLD_TEXT,
              fontFamily: nunito.style.fontFamily,
              fontWeight: 900,
              fontSize: '14px',
              borderRadius: '999px',
              px: '12px',
              py: '4px',
            }}
          >
            ⭐ {bot.rating}
          </Box>
        </Box>

        <Typography
          component="p"
          sx={{
            fontFamily: nunito.style.fontFamily,
            fontWeight: 700,
            fontSize: '15px',
            color: INK_SOFT,
            lineHeight: 1.45,
            maxWidth: 380,
            mx: 'auto',
            mb: '30px',
          }}
        >
          {botDescription(t, bot)}
        </Typography>

        {/* Color picker */}
        <Typography
          component="div"
          sx={{
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 600,
            fontSize: '16px',
            color: INK,
            textAlign: 'left',
            mb: '10px',
          }}
        >
          {playText(t, 'playAs', 'Play as')}
        </Typography>
        <Box sx={{ display: 'flex', gap: '12px', mb: '28px' }}>
          {COLOR_OPTIONS.map((opt) => {
            const selected = playerColor === opt.value
            return (
              <Box
                key={opt.value}
                role="radio"
                aria-checked={selected}
                tabIndex={0}
                onClick={() => onColorChange(opt.value)}
                onKeyDown={(e: React.KeyboardEvent) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onColorChange(opt.value)
                  }
                }}
                sx={{
                  flex: 1,
                  textAlign: 'center',
                  cursor: 'pointer',
                  borderRadius: '14px',
                  py: '14px',
                  fontFamily: nunito.style.fontFamily,
                  fontWeight: 800,
                  fontSize: '15px',
                  border: `2.5px solid ${selected ? main : '#D8E4EE'}`,
                  bgcolor: selected ? tint : '#fff',
                  color: selected ? deep : INK_SOFT,
                  boxShadow: selected ? `0 4px 12px ${main}4D` : 'none',
                  transition: 'border-color 120ms ease, background-color 120ms ease',
                  '&:focus-visible': { outline: `3px solid ${main}`, outlineOffset: '2px' },
                }}
              >
                <Box component="span" aria-hidden="true" sx={{ display: 'block', fontSize: '26px', mb: '4px' }}>
                  {opt.glyph}
                </Box>
                {playText(t, opt.labelKey, opt.fallback)}
              </Box>
            )
          })}
        </Box>

        {/* Play CTA */}
        <Box
          component="button"
          type="button"
          onClick={onPlay}
          disabled={disabled}
          sx={{
            display: 'block',
            width: '100%',
            border: 'none',
            cursor: disabled ? 'default' : 'pointer',
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 700,
            fontSize: '22px',
            color: '#fff',
            background: world.headerGradient,
            borderRadius: '16px',
            py: '18px',
            boxShadow: `0 6px 0 ${deep}, 0 14px 26px ${deep}47`,
            opacity: disabled ? 0.6 : 1,
            transition: 'transform 120ms ease, box-shadow 120ms ease',
            '&:hover': disabled
              ? {}
              : { transform: 'translateY(2px)', boxShadow: `0 4px 0 ${deep}, 0 10px 20px ${deep}47` },
          }}
        >
          {playText(t, 'playAgainst', `Play against ${bot.name}`, { name: bot.name })}{' '}
          <Box component="span" aria-hidden="true">
            {world.emoji}
          </Box>
        </Box>
      </Box>
    </Paper>
  )
}
