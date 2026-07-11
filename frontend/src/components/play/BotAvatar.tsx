'use client'

import React, { useState } from 'react'
import { Box } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import type { Bot } from '@/data/bots'
import { fredoka } from '@/lib/fonts'

interface BotAvatarProps {
  bot: Bot
  /** Diameter in px. */
  size: number
  /** Ring border color (defaults to white). */
  ringColor?: string
  /** Ring border width in px. */
  ringWidth?: number
  /** Background/fallback tint behind the image and emoji. */
  tint: string
  /** Color for the fallback emoji/initial. */
  deep: string
  /** Pulse while the bot is thinking. */
  thinking?: boolean
  /** Pulse ring color (defaults to `deep`). */
  pulseColor?: string
  sx?: SxProps<Theme>
}

/**
 * Circular bot portrait with graceful fallback: shows the avatar image when
 * present and loadable, otherwise the bot emoji (or name initial) on a tinted
 * circle. Falls back automatically if the image 404s — avatar files for some
 * bots may land after this ships.
 */
export default function BotAvatar({
  bot,
  size,
  ringColor = '#fff',
  ringWidth = 4,
  tint,
  deep,
  thinking = false,
  pulseColor,
  sx,
}: BotAvatarProps) {
  const [errored, setErrored] = useState(false)
  const showImage = Boolean(bot.avatar) && !errored
  const pulse = pulseColor ?? deep

  return (
    <Box
      data-testid="bot-avatar"
      sx={{
        width: size,
        height: size,
        borderRadius: '50%',
        overflow: 'hidden',
        flexShrink: 0,
        bgcolor: tint,
        border: `${ringWidth}px solid ${ringColor}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...(thinking && {
          animation: 'botAvatarPulse 1.2s ease-in-out infinite',
          '@keyframes botAvatarPulse': {
            '0%, 100%': {
              transform: 'scale(1)',
              boxShadow: `0 0 0 0 ${pulse}66`,
            },
            '50%': {
              transform: 'scale(1.05)',
              boxShadow: `0 0 0 8px ${pulse}00`,
            },
          },
        }),
        ...sx,
      }}
    >
      {showImage ? (
        <Box
          component="img"
          src={bot.avatar}
          alt={bot.name}
          onError={() => setErrored(true)}
          sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      ) : (
        <Box
          data-testid="bot-avatar-fallback"
          component="span"
          aria-hidden="true"
          sx={{
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 700,
            fontSize: size * 0.42,
            lineHeight: 1,
            color: deep,
          }}
        >
          {bot.emoji ?? bot.name[0]}
        </Box>
      )}
    </Box>
  )
}
