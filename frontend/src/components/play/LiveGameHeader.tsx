'use client'

import React from 'react'
import { Box, Typography } from '@mui/material'
import { fredoka, nunito } from '@/lib/fonts'
import { LIVE_PLAY_THEME, LIVE_INK, LIVE_INK_SOFT } from '@/lib/livePlayTheme'

interface LiveGameHeaderProps {
  /** Opponent display name. */
  opponentName: string
  /** Presence dot — green when the opponent is connected. */
  connected: boolean
  /** Preformatted opponent clock (e.g. "5:00" / "∞"). */
  clock: string
  /** Highlight the clock while it's the opponent's move. */
  clockActive: boolean
}

/** First letter of a name, for the initial-letter avatar. */
function initial(name: string): string {
  return (name.trim()[0] ?? '?').toUpperCase()
}

/**
 * Online-play header card — a rounded white card with the opponent's
 * initial-letter avatar, username, a presence dot (from `opponentConnected`),
 * and their clock. Mirrors the bot game's `GameHeader` slot but is opponent-
 * driven rather than bot-themed.
 */
export default function LiveGameHeader({
  opponentName,
  connected,
  clock,
  clockActive,
}: LiveGameHeaderProps) {
  const { main, tint, deep } = LIVE_PLAY_THEME
  return (
    <Box
      data-testid="live-game-header"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.25,
        bgcolor: 'rgba(255,255,255,.95)',
        borderRadius: '18px',
        p: 1.25,
        boxShadow: `0 10px 26px ${deep}33`,
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          width: 48,
          height: 48,
          borderRadius: '16px',
          bgcolor: tint,
          color: deep,
          border: `2px solid ${main}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: fredoka.style.fontFamily,
          fontWeight: 700,
          fontSize: 24,
          flexShrink: 0,
        }}
      >
        {initial(opponentName)}
      </Box>
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography
          component="div"
          sx={{
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 700,
            fontSize: '18px',
            color: LIVE_INK,
            lineHeight: 1.15,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {opponentName}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mt: 0.25 }}>
          <Box
            data-testid="presence-dot"
            data-connected={connected}
            aria-hidden="true"
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              bgcolor: connected ? '#22C55E' : '#CBD5E1',
              flexShrink: 0,
            }}
          />
          <Typography
            component="span"
            sx={{
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '12px',
              color: LIVE_INK_SOFT,
            }}
          >
            {connected ? 'Online' : 'Offline'}
          </Typography>
        </Box>
      </Box>
      <Box
        data-testid="opponent-clock"
        sx={{
          px: 1.75,
          py: 0.75,
          borderRadius: '12px',
          bgcolor: clockActive ? LIVE_INK : '#EEF2FA',
          color: clockActive ? '#fff' : LIVE_INK,
          fontFamily: nunito.style.fontFamily,
          fontVariantNumeric: 'tabular-nums',
          fontWeight: 900,
          fontSize: 20,
          minWidth: 72,
          textAlign: 'center',
          flexShrink: 0,
        }}
      >
        {clock}
      </Box>
    </Box>
  )
}
